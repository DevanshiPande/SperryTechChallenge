from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.deps import ident, json_body
from services import jobs as svc

router = APIRouter()


@router.get("/jobs")
def list_jobs(q: Optional[str] = None, near: Optional[str] = None, radius_km: Optional[str] = None,
              qualification: Optional[str] = None, status: Optional[str] = "open"):
    return svc.list_jobs(q, near, radius_km, qualification, None if status in (None, "", "all") else status)


@router.get("/saved-jobs")
def list_saved_jobs(who=Depends(ident)):
    return svc.list_saved_jobs(who)


@router.post("/jobs")
def create_job(body: dict = Depends(json_body), who=Depends(ident)):
    return JSONResponse(svc.create_job(who, body), status_code=201)


@router.get("/jobs/{jid}")
def get_job(jid: str):
    return svc.get_job(jid)


@router.post("/jobs/{jid}/save")
def save_job(jid: str, who=Depends(ident)):
    return JSONResponse(svc.save_job(who, jid), status_code=201)


@router.delete("/jobs/{jid}/save")
def unsave_job(jid: str, who=Depends(ident)):
    return svc.unsave_job(who, jid)


@router.patch("/jobs/{jid}")
def update_job(jid: str, body: dict = Depends(json_body), who=Depends(ident)):
    return svc.update_job(who, jid, body)


@router.post("/jobs/{jid}/applications")
def apply(jid: str, body: dict = Depends(json_body), who=Depends(ident)):
    return JSONResponse(svc.apply(who, jid, body), status_code=201)


@router.get("/applications")
def list_applications(who=Depends(ident)):
    return svc.list_applications(who)


@router.patch("/applications/{app_id}")
def update_application(app_id: str, body: dict = Depends(json_body), who=Depends(ident)):
    return svc.update_application(who, app_id, body.get("status"))
