from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from app.database import create_tables
from app.auth.router import router as auth_router
from app.billing.router import router as billing_router
from app.routers.nba import router as nba_router
from app.routers.nfl import router as nfl_router
from app.routers.mlb import router as mlb_router
from app.config import settings

app = FastAPI(title="Sports Analytics API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _run_migrations():
    """Add any new columns to existing tables without losing data."""
    from app.database import engine
    from sqlalchemy import text
    new_columns = [
        "ALTER TABLE users ADD COLUMN first_name VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN last_name VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN state VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN favorite_sport VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN favorite_teams VARCHAR(500)",
    ]
    with engine.connect() as conn:
        for sql in new_columns:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # Column already exists — safe to ignore

@app.on_event("startup")
def startup():
    create_tables()
    _run_migrations()
    # Pre-warm MLB data cache so first user request doesn't time out
    try:
        from app.data.loader import get_mlb_data, get_pitcher_names
        get_mlb_data()
        get_pitcher_names()
    except Exception:
        pass

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(billing_router, prefix="/billing", tags=["billing"])
app.include_router(nba_router)
app.include_router(nfl_router)
app.include_router(mlb_router)

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/clear-cache")
def clear_cache():
    """Clear all lru_cache data caches so fresh data is fetched on next request."""
    from app.data.loader import (
        get_nba_data, get_nfl_stats, get_nfl_team_stats,
        get_nfl_schedule, get_nba_props, get_mlb_data,
        get_mlb_props_data, get_pitcher_names,
    )
    get_nba_data.cache_clear()
    get_nfl_stats.cache_clear()
    get_nfl_team_stats.cache_clear()
    get_nfl_schedule.cache_clear()
    get_nba_props.cache_clear()
    get_mlb_data.cache_clear()
    get_mlb_props_data.cache_clear()
    get_pitcher_names.cache_clear()
    return {"status": "cache cleared"}

@app.get("/api/db-test")
def db_test():
    """Diagnostic endpoint — tests DB connection and returns result."""
    import time
    from app.database import engine
    from sqlalchemy import text
    try:
        start = time.time()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).fetchone()
        elapsed = round((time.time() - start) * 1000)
        db_url_safe = settings.DATABASE_URL[:30] + "..." if len(settings.DATABASE_URL) > 30 else settings.DATABASE_URL
        return {"db": "ok", "ms": elapsed, "url_prefix": db_url_safe}
    except Exception as e:
        return {"db": "error", "error": str(e)}

STATIC_DIR = os.path.join(os.path.dirname(__file__), "../../frontend/dist")
if os.path.exists(STATIC_DIR):
    STATIC_DIR_ABS = os.path.realpath(STATIC_DIR)

    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        # Never intercept backend routes
        if full_path.startswith(("api/", "auth/", "billing/")):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")

        # Serve a real static file if one exists at this path (e.g. anything
        # from the frontend's public/ folder -- nfl-logos/*.jpg, favicon.svg,
        # icons.svg -- which previously only worked for /assets and silently
        # fell through to index.html for everything else, making every
        # public/ asset 404-as-the-homepage in production).
        #
        # realpath + startswith guards against path traversal (e.g.
        # full_path="../../etc/passwd") since full_path comes straight from
        # the URL and is otherwise untrusted.
        if full_path:
            candidate = os.path.realpath(os.path.join(STATIC_DIR, full_path))
            if candidate.startswith(STATIC_DIR_ABS + os.sep) and os.path.isfile(candidate):
                return FileResponse(candidate)

        index = os.path.join(STATIC_DIR, "index.html")
        if not os.path.exists(index):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Frontend not built")
        return FileResponse(index)
