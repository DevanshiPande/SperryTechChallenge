"""Gridlock API. Run from backend/:  uvicorn api.main:app --reload"""
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_dotenv(path=Path(__file__).resolve().parents[1] / ".env"):
    """Local development: KEY=VALUE lines from backend/.env. Real env vars win. Never committed (see .gitignore)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


if "pytest" not in sys.modules:
    load_dotenv()

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from api.routers import (agent, contracts, events, export, gemini_routes, jobs, messages, ml,  # noqa: E402
                         overlaps, projects, quality, reservations, resources, system, traffic, whatif)
from services.errors import ApiError  # noqa: E402

log = logging.getLogger("gridlock")


def startup(state=None, db=None, connect=True):
    """Load public data into memory, connect Mongo (or read-only mode), seed."""
    from ai import gemini
    from db import mongo, seed
    from services.state import STATE
    state = state or STATE
    if not state.projects:
        state.load_files()
    from services import ml as ml_models
    ml_models.available()  # load ml/predict.py and the trained models once
    if state.traffic is None:
        from services import traffic
        from services.state import data_dir
        state.traffic = traffic.load(str(data_dir() / "traffic"))
    state.db = db if db is not None else (mongo.connect() if connect else None)
    if state.db is not None:
        seed.run(state.db, state.projects, state.overlaps)
        gemini.set_cache(MongoGeminiCache(state.db))
    log.info("loaded %d public projects, %d overlaps; mode=%s", len(state.projects), len(state.overlaps),
             "mongo" if state.db is not None else "read-only")


class MongoGeminiCache:
    def __init__(self, db):
        self.db = db

    def get(self, key):
        d = self.db.gemini_cache.find_one({"key": key})
        return d["response"] if d else None

    def set(self, key, value):
        from datetime import datetime, timezone
        from db.mongo import now
        self.db.gemini_cache.update_one({"key": key}, {"$set": {"key": key, "response": value, "created_at": now(),
                                                                "created_at_dt": datetime.now(timezone.utc)}},
                                        upsert=True)


def _reconnect_loop(stop, every_s=30):
    """Read-only because Mongo was unreachable at startup (e.g. IP not on the Atlas access list):
    keep retrying, and switch to database mode (seed included) as soon as it answers."""
    from ai import gemini
    from db import mongo, seed
    from services.state import STATE
    while not stop.wait(every_s):
        if STATE.db is not None:
            return
        db = mongo.connect()
        if db is not None:
            seed.run(db, STATE.projects, STATE.overlaps)
            gemini.set_cache(MongoGeminiCache(db))
            STATE.db = db
            log.info("MongoDB reachable again: switched from read-only to database mode")
            return


@asynccontextmanager
async def lifespan(app):
    import threading
    stop = threading.Event()
    if not getattr(app.state, "skip_startup", False):
        startup()
        from services.state import STATE
        if STATE.db is None and os.environ.get("MONGO_URI"):
            threading.Thread(target=_reconnect_loop, args=(stop,), daemon=True).start()
        if STATE.traffic is not None and os.environ.get("GRIDLOCK_WARM_CONGESTION", "1") != "0":
            # Pre-compute predicted congestion (and its Gemini summary) for every project in the background.
            from services import congestion
            threading.Thread(target=congestion.warm_all, args=(stop,), daemon=True).start()
    yield
    stop.set()


def create_app(skip_startup=False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(title="Gridlock API", version="1.0", lifespan=lifespan)
    app.state.skip_startup = skip_startup
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "X-Company-Id", "X-Worker-Id"])

    @app.exception_handler(ApiError)
    async def api_error(_: Request, e: ApiError):
        return JSONResponse(e.body(), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        parts = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err.get("loc", []) if x not in ("body", "query", "path"))
            parts.append(f"{loc}: {err.get('msg')}" if loc else err.get("msg"))
        return JSONResponse({"error": {"code": "BAD_REQUEST", "message": "; ".join(parts) or "Invalid request"}},
                            status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, e: StarletteHTTPException):
        if e.status_code == 404:
            msg = f"No route for {request.method} {request.url.path}"
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": msg}}, status_code=404)
        if e.status_code == 405:
            return JSONResponse({"error": {"code": "BAD_REQUEST", "message": "Method not allowed"}}, status_code=405)
        return JSONResponse({"error": {"code": "BAD_REQUEST", "message": str(e.detail)}}, status_code=e.status_code)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, e: Exception):
        log.exception("unhandled error")
        return JSONResponse({"error": {"code": "INTERNAL", "message": "Internal server error"}}, status_code=500)

    for r in (system, projects, overlaps, quality, whatif, export, events, resources, reservations, jobs, messages,
              gemini_routes, agent, traffic, contracts, ml):
        app.include_router(r.router)
    return app


app = create_app()
