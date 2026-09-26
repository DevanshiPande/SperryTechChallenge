from fastapi import APIRouter, Depends

from api.deps import json_body
from services import public

router = APIRouter()


@router.post("/whatif")
def whatif(body: dict = Depends(json_body)):
    return public.run_whatif(body)
