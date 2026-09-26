from fastapi import APIRouter, Depends

from ai import agent, features
from api.deps import ident, json_body

router = APIRouter()


@router.post("/overlaps/{oid}/brief")
def brief(oid: str, body: dict = Depends(json_body)):
    return features.brief(oid, body.get("mode") or "summary", bool(body.get("refresh")))


@router.post("/draft")
def draft(body: dict = Depends(json_body)):
    return features.draft(body.get("kind"), body.get("text", ""), body.get("draft"))


@router.post("/scenario/assist")
def scenario_assist(body: dict = Depends(json_body)):
    return features.scenario_assist(body.get("overlap_id"), body.get("message", ""), body.get("scenario"))


@router.post("/ask")
def ask(body: dict = Depends(json_body), who=Depends(ident)):
    return agent.ask(who, body.get("question", ""), body.get("context"))
