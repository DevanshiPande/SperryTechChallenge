from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.deps import ident, json_body
from services import resources as svc

router = APIRouter()


@router.get("/resources")
def list_resources(type: Optional[str] = None, near: Optional[str] = None, radius_km: Optional[str] = None,
                   q: Optional[str] = None, company_id: Optional[str] = None, available_on: Optional[str] = None):
    return svc.list_resources(type, near, radius_km, q, company_id, available_on)


@router.get("/resources/{rid}")
def get_resource(rid: str):
    return svc.get_resource(rid)


@router.post("/resources")
def create_resource(body: dict = Depends(json_body), who=Depends(ident)):
    return JSONResponse(svc.create_resource(who, body), status_code=201)


@router.patch("/resources/{rid}")
def update_resource(rid: str, body: dict = Depends(json_body), who=Depends(ident)):
    return svc.update_resource(who, rid, body)


@router.delete("/resources/{rid}")
def delete_resource(rid: str, who=Depends(ident)):
    return svc.delete_resource(who, rid)
