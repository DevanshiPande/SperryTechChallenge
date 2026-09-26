from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.deps import ident, json_body
from services import messages as svc

router = APIRouter()


@router.get("/conversations")
def list_conversations(who=Depends(ident)):
    return svc.list_conversations(who)


@router.post("/conversations")
def create_conversation(body: dict = Depends(json_body), who=Depends(ident)):
    return JSONResponse(svc.create_conversation(who, body), status_code=201)


@router.get("/conversations/{cid}/messages")
def list_messages(cid: str, who=Depends(ident)):
    return svc.list_messages(who, cid)


@router.post("/conversations/{cid}/messages")
def post_message(cid: str, body: dict = Depends(json_body), who=Depends(ident)):
    return JSONResponse(svc.post_message(who, cid, body), status_code=201)
