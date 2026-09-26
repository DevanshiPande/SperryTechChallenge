from typing import Optional

from fastapi import APIRouter

from services import projects as svc

router = APIRouter()


@router.get("/overlaps")
def list_overlaps(max_mi: Optional[str] = None, tier: Optional[str] = None, potential: Optional[str] = None,
                  min_window_overlap_months: Optional[str] = None, year_from: Optional[str] = None,
                  year_to: Optional[str] = None, q: Optional[str] = None, sort: Optional[str] = None,
                  kind: Optional[str] = None, project_id: Optional[str] = None):
    """project_id (additive): only the opportunities involving that project, best first."""
    return svc.list_overlaps(max_mi, tier, potential, min_window_overlap_months, year_from, year_to, q, sort, kind, project_id)


@router.get("/overlaps/{oid}")
def get_overlap(oid: str):
    return svc.get_overlap(oid)
