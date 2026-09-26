from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.deps import ident, json_body
from services import resources as svc

router = APIRouter()


@router.post("/resources/{rid}/reservations")
def create_reservation(rid: str, body: dict = Depends(json_body), who=Depends(ident)):
    return JSONResponse(svc.create_reservation(who, rid, body), status_code=201)


@router.get("/reservations")
def list_reservations(role: Optional[str] = None, who=Depends(ident)):
    return svc.list_reservations(who, role)


@router.patch("/reservations/{rsv_id}")
def update_reservation(rsv_id: str, body: dict = Depends(json_body), who=Depends(ident)):
    return svc.update_reservation(who, rsv_id, body.get("status"))
