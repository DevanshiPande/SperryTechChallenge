from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import json_body
from services import traffic as svc

router = APIRouter()


@router.get("/traffic/crossings")
def crossings(project_id: Optional[str] = None, road_ref: Optional[str] = None, min_aadt: Optional[str] = None):
    return svc.list_crossings(project_id, road_ref, min_aadt)


@router.get("/traffic/crossings/{crossing_id}")
def crossing(crossing_id: str):
    return svc.get_crossing(crossing_id)


@router.get("/traffic/conflicts")
def conflicts(kind: Optional[str] = None, min_delay: Optional[str] = None):
    return svc.list_conflicts(kind, min_delay)


@router.post("/traffic/plan")
def plan(body: dict = Depends(json_body)):
    return svc.plan_request(body)


@router.post("/traffic/crossings/{crossing_id}/brief")
def crossing_brief(crossing_id: str, body: dict = Depends(json_body)):
    from ai import features
    return features.crossing_brief(crossing_id, bool(body.get("refresh")))


@router.get("/traffic/summary")
def summary():
    return svc.summary()


@router.get("/projects/{pid}/congestion")
def congestion(pid: str):
    """Predicted congestion on the roads around a project (for the map), with a plain-English summary."""
    from services import congestion as csvc
    return csvc.project_congestion(pid)
