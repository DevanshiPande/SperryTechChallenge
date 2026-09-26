from fastapi import APIRouter, Depends

from api.deps import ident
from services import events
from services.errors import bad_request

router = APIRouter()


@router.get("/events")
def get_events(since: str = "0", who=Depends(ident)):
    try:
        seq = int(since)
    except ValueError:
        raise bad_request("since must be an integer")
    return events.since(seq, who.company_id)
