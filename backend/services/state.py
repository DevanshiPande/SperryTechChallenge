"""Process-wide state: public data in memory (always), Mongo handle (or None in read-only mode)."""
import json
import os
from datetime import date
from pathlib import Path

from services.errors import db_unavailable

BACKEND = Path(__file__).resolve().parents[1]


def data_dir():
    d = os.environ.get("DATA_DIR")
    if not d:
        return BACKEND / "data"
    p = Path(d)
    return p if p.is_absolute() else (BACKEND.parent / p if (BACKEND.parent / p).exists() else BACKEND / p)


class State:
    def __init__(self):
        self.projects = []  # public projects
        self.projects_by_id = {}
        self.overlaps = []  # public (cross_utility) overlaps
        self.overlaps_by_id = {}
        self.db = None
        self.briefs = {}  # (overlap_id, mode) -> {brief, source}, used when there is no DB
        self.generated_at = None
        self.traffic = None  # services.traffic.TrafficIndex when data/traffic is present
        self.contracts = {}  # contract drafts kept in memory when there is no DB

    def load(self, projects, overlaps, generated_at=None):
        self.projects = projects
        self.projects_by_id = {p["id"]: p for p in projects}
        self.overlaps = overlaps
        self.overlaps_by_id = {o["id"]: o for o in overlaps}
        self.generated_at = generated_at or date.today().isoformat()

    def load_files(self, directory=None):
        d = Path(directory) if directory else data_dir()
        pf, of = d / "projects.json", d / "overlaps.json"
        projects = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else []
        overlaps = json.loads(of.read_text(encoding="utf-8")) if of.exists() else []
        gen = date.fromtimestamp(pf.stat().st_mtime).isoformat() if pf.exists() else None
        self.load(projects, overlaps, gen)


STATE = State()


def require_db():
    if STATE.db is None:
        raise db_unavailable()
    return STATE.db
