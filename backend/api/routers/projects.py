from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.deps import ident, json_body
from services import projects as svc

router = APIRouter()


@router.get("/projects")
def list_projects(utility: Optional[str] = None, confidence: Optional[str] = None, has_overlap: Optional[str] = None,
                  year_from: Optional[str] = None, year_to: Optional[str] = None, q: Optional[str] = None,
                  source: Optional[str] = None):
    return svc.list_projects(utility, confidence, has_overlap, year_from, year_to, q, source)


@router.get("/projects/{pid}")
def get_project(pid: str):
    p = svc.get_project(pid)
    p["traffic"] = svc.project_traffic(p)
    return p


@router.post("/projects")
def create_project(body: dict = Depends(json_body), who=Depends(ident)):
    return JSONResponse(svc.create_user_project(who, body), status_code=201)


@router.patch("/projects/{pid}")
def update_project(pid: str, body: dict = Depends(json_body), who=Depends(ident)):
    return svc.update_user_project(who, pid, body)


@router.delete("/projects/{pid}")
def delete_project(pid: str, who=Depends(ident)):
    return svc.delete_user_project(who, pid)
