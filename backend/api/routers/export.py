from fastapi import APIRouter
from fastapi.responses import Response

from services import public

router = APIRouter()


@router.get("/export/overlaps.xlsx")
def export_overlaps():
    return Response(public.export_xlsx(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="overlaps.xlsx"'})
