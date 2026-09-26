from fastapi import APIRouter, Depends

from ai import agent
from api.deps import ident, json_body

router = APIRouter()


@router.post("/agent/chat")
def chat(body: dict = Depends(json_body), who=Depends(ident)):
    return agent.chat(who, body.get("message"), body.get("thread_id"), body.get("context"))


@router.post("/agent/actions/{action_id}/confirm")
def confirm(action_id: str, body: dict = Depends(json_body), who=Depends(ident)):
    return agent.confirm(who, action_id, body.get("args"))


@router.post("/agent/actions/{action_id}/cancel")
def cancel(action_id: str, who=Depends(ident)):
    return agent.cancel(who, action_id)


@router.get("/agent/threads/{thread_id}")
def get_thread(thread_id: str, who=Depends(ident)):
    return agent.get_thread(who, thread_id)
