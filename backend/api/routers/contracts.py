from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from api.deps import ident, json_body
from services import contracts as svc

router = APIRouter()


@router.post("/contracts/analyze")
async def analyze(file: UploadFile = File(...), who=Depends(ident)):
    data = await file.read(svc.MAX_BYTES + 1)
    return JSONResponse(svc.analyze(who, file.filename, data), status_code=201)


@router.get("/contracts/{cid}")
def get_contract(cid: str, who=Depends(ident)):
    d = svc.get_contract(who, cid)
    return {k: v for k, v in d.items() if k != "text_hash"}


@router.post("/contracts/{cid}/match")
def match(cid: str, body: dict = Depends(json_body), who=Depends(ident)):
    return svc.match(who, cid, body.get("fields") or body)


@router.post("/contracts/{cid}/save")
def save(cid: str, who=Depends(ident)):
    return JSONResponse(svc.save(who, cid), status_code=201)
