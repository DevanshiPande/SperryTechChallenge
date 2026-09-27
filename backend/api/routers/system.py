from fastapi import APIRouter, Depends

from api.deps import ident, json_body
from services import identity, public
from services.errors import ApiError
from services.geocode import geocode

router = APIRouter()


@router.get("/health")
def health():
    from services.state import STATE
    return {"status": "ok", "db": "connected" if STATE.db is not None else "read-only"}


@router.get("/meta")
def meta():
    return public.meta()


@router.get("/companies")
def companies():
    return [{"id": c["id"], "name": c["name"], "yard": c.get("yard"), "phone": c.get("phone")}
            for c in identity.companies()]


@router.get("/me")
def me(who=Depends(ident)):
    out = {"kind": who.kind}
    if who.company:
        out["company"] = who.company
    if who.worker:
        out["worker"] = who.worker
    return out


@router.patch("/me")
def update_me(body: dict = Depends(json_body), who=Depends(ident)):
    """Workers edit their own profile (trade, certifications, experience, availability, service_area_text)."""
    return identity.update_worker(who, body)


@router.get("/geocode")
def geocode_text(q: str):
    """Free-text place -> {lat, lon, label} via Nominatim (never Gemini). Used by map pins and 'near' filters."""
    g = geocode(q)
    if not g:
        raise ApiError("NOT_FOUND", f'Could not locate "{q}". Try a town name.')
    return g
