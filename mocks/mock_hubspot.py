"""Mock HubSpot CRM API for practice (milestone B).

It copies the shape of HubSpot's CRM objects API (v3 paths) closely enough that
your sync code should only need a different base URL and token to talk to the
real thing. Simplifications are marked "SIMPLIFIED".

Run it on the server (from the repository's top folder):

    uvicorn mocks.mock_hubspot:app --host 127.0.0.1 --port 8001

Then open http://localhost:8001/docs (through an SSH tunnel) to see every endpoint.

Switches (environment variables) that make it misbehave on purpose:
    MOCK_HUBSPOT_TOKEN   the token your code must send (default: fake-hubspot-token)
    MOCK_PAGE_SIZE       most results per page, to force paging (default: 2)
    MOCK_FAIL_EVERY      every Nth call gets a 429 "too many requests" (default: 0 = never)
    MOCK_SLOW_SECONDS    wait this long before every reply (default: 0)

Example: MOCK_FAIL_EVERY=3 uvicorn mocks.mock_hubspot:app --host 127.0.0.1 --port 8001
"""

import copy
import itertools
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse

DATA_FILE = Path(__file__).with_name("hubspot_data.json")
FAKE_TOKEN = os.environ.get("MOCK_HUBSPOT_TOKEN", "fake-hubspot-token")
PAGE_SIZE_CAP = int(os.environ.get("MOCK_PAGE_SIZE", "2"))
FAIL_EVERY = int(os.environ.get("MOCK_FAIL_EVERY", "0"))
SLOW_SECONDS = float(os.environ.get("MOCK_SLOW_SECONDS", "0"))

# The fake database. It lives in memory, so restarting the mock resets any PATCH changes.
DATA = json.loads(DATA_FILE.read_text())
_call_counter = itertools.count(1)

app = FastAPI(
    title="Mock HubSpot CRM",
    description="A practice stand-in for HubSpot's CRM API. Fake data only.",
)


# ---------- Errors shaped like HubSpot's ----------

class HubSpotError(Exception):
    """Raise this anywhere to send HubSpot-style error JSON."""

    def __init__(self, status_code, category, message, headers=None):
        self.status_code = status_code
        self.category = category
        self.message = message
        self.headers = headers


@app.exception_handler(HubSpotError)
async def hubspot_error_handler(request: Request, exc: HubSpotError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "category": exc.category, "message": exc.message},
        headers=exc.headers,
    )


# ---------- Checks that run before every API call ----------

def check_request(authorization: str | None = Header(default=None)):
    """Require the bearer token, then apply the misbehaviour switches."""
    if authorization != f"Bearer {FAKE_TOKEN}":
        raise HubSpotError(401, "INVALID_AUTHENTICATION", "Authentication credentials not found.")

    call_number = next(_call_counter)
    if SLOW_SECONDS:
        time.sleep(SLOW_SECONDS)
    if FAIL_EVERY and call_number % FAIL_EVERY == 0:
        raise HubSpotError(
            429, "RATE_LIMITS", "You have reached your secondly limit.",
            headers={"Retry-After": "1"},
        )


# ---------- Helpers ----------

def get_collection(object_type):
    if object_type not in DATA:
        raise HubSpotError(400, "VALIDATION_ERROR", f"Unable to infer object type from: {object_type}")
    return DATA[object_type]


def find_record(object_type, object_id):
    for record in get_collection(object_type):
        if record["id"] == object_id:
            return record
    raise HubSpotError(404, "OBJECT_NOT_FOUND", "resource not found")


def split_list(value):
    """Turn 'a,b,c' into ['a', 'b', 'c']; None or '' into []."""
    return [part.strip() for part in value.split(",") if part.strip()] if value else []


def singular(object_type):
    return {"companies": "company", "deals": "deal", "quotes": "quote", "line_items": "line_item"}.get(
        object_type, object_type
    )


def shape(object_type, record, properties, associations):
    """Build one object the way HubSpot returns it."""
    all_props = record["properties"]
    if properties:
        # SIMPLIFIED: real HubSpot also adds a few default properties (createdate etc.).
        props = {k: all_props.get(k) for k in properties}
        props["hs_object_id"] = all_props["hs_object_id"]
    else:
        props = dict(all_props)

    result = {
        "id": record["id"],
        "properties": props,
        "createdAt": record["createdAt"],
        "updatedAt": record["updatedAt"],
        "archived": False,
    }

    linked = {}
    for other_type in associations:
        ids = record.get("associations", {}).get(other_type, [])
        if ids:
            link_type = f"{singular(object_type)}_to_{singular(other_type)}"
            linked[other_type] = {"results": [{"id": i, "type": link_type} for i in ids]}
    if linked:
        result["associations"] = linked
    return result


# ---------- Endpoints ----------

@app.get("/", include_in_schema=False)
def home():
    return {"message": "Mock HubSpot is running. See /docs for the endpoints."}


@app.get("/crm/v3/objects/{object_type}", dependencies=[Depends(check_request)])
def list_objects(
    object_type: str,
    limit: int = Query(10, ge=1, le=100),
    after: str | None = None,
    properties: str | None = None,
    associations: str | None = None,
):
    """List objects one page at a time. Pass paging.next.after back as ?after= for the next page."""
    records = get_collection(object_type)
    page_size = min(limit, PAGE_SIZE_CAP) if PAGE_SIZE_CAP else limit
    start = int(after) if after else 0  # SIMPLIFIED: real "after" values are opaque strings
    page = records[start:start + page_size]

    body = {
        "results": [
            shape(object_type, r, split_list(properties), split_list(associations)) for r in page
        ]
    }
    next_start = start + page_size
    if next_start < len(records):
        body["paging"] = {
            "next": {
                "after": str(next_start),
                "link": f"/crm/v3/objects/{object_type}?after={next_start}&limit={limit}",
            }
        }
    return body


@app.get("/crm/v3/objects/{object_type}/{object_id}", dependencies=[Depends(check_request)])
def get_object(
    object_type: str,
    object_id: str,
    properties: str | None = None,
    associations: str | None = None,
):
    """Get one object by id, e.g. /crm/v3/objects/quotes/5001?associations=line_items"""
    record = find_record(object_type, object_id)
    return shape(object_type, record, split_list(properties), split_list(associations))


@app.patch("/crm/v3/objects/{object_type}/{object_id}", dependencies=[Depends(check_request)])
def update_object(object_type: str, object_id: str, payload: dict = Body(...)):
    """Update properties, e.g. body {"properties": {"float_project_id": "123"}}"""
    record = find_record(object_type, object_id)
    new_props = payload.get("properties")
    if not isinstance(new_props, dict):
        raise HubSpotError(400, "VALIDATION_ERROR", "Request body must contain a 'properties' object.")

    # Like HubSpot, refuse properties that don't exist on this object type.
    known = set().union(*(r["properties"].keys() for r in get_collection(object_type)))
    unknown = sorted(set(new_props) - known)
    if unknown:
        raise HubSpotError(400, "VALIDATION_ERROR", f"Property values were not valid: {', '.join(unknown)} does not exist")

    # HubSpot stores property values as strings.
    for key, value in new_props.items():
        record["properties"][key] = None if value is None else str(value)
    record["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return shape(object_type, copy.deepcopy(record), [], [])
