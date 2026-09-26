import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ["FAKE_GEMINI"] = "1"
os.environ["FAKE_GEOCODER"] = "1"
os.environ.pop("MONGO_URI", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)

XLSX = BACKEND / "data" / "raw" / "Projects_Overlaps.xlsx"


def starter_data():
    """Sperry's 10 starter projects + their 6 overlaps: small, known fixture data."""
    from engine.overlaps import cross_utility_overlaps
    from pipeline.starter import starter_projects
    projects = starter_projects(XLSX)
    for p in projects:
        p["source"]["type"] = "public_filing"
    overlaps = cross_utility_overlaps(projects)
    by_id = {p["id"]: p for p in projects}
    for o in overlaps:
        by_id[o["project_a"]]["overlap_ids"].append(o["id"])
        by_id[o["project_b"]]["overlap_ids"].append(o["id"])
    return projects, overlaps


def _reset():
    from ai import gemini
    from services import geocode
    from services.state import STATE
    gemini.fake_reset()
    gemini.set_cache(gemini.MemoryCache())
    geocode._memory.clear()
    STATE.__init__()
    return STATE


def _client(db):
    from fastapi.testclient import TestClient
    from api.main import create_app, startup
    state = _reset()
    projects, overlaps = starter_data()
    state.load(projects, overlaps, "2026-09-26")
    startup(state=state, db=db, connect=False)
    return TestClient(create_app(skip_startup=True))


@pytest.fixture
def client_ro():
    """Read-only mode: no Mongo."""
    c = _client(None)
    yield c
    _reset()


@pytest.fixture
def mdb():
    import mongomock
    return mongomock.MongoClient(tz_aware=True)["gridlock_test"]


@pytest.fixture
def client(mdb):
    """Mongo mode (mongomock) with seeded demo companies."""
    c = _client(mdb)
    yield c
    _reset()


def as_company(cid):
    return {"X-Company-Id": cid}
