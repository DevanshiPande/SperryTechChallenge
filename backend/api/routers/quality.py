from fastapi import APIRouter

from services import public

router = APIRouter()


@router.get("/quality")
def quality():
    return public.quality_list()
