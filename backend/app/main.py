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

@app.on_event("startup")
def startup():
    create_tables()

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(billing_router, prefix="/billing", tags=["billing"])
app.include_router(nba_router)
app.include_router(nfl_router)
app.include_router(mlb_router)

@app.get("/api/health")
def health():
    return {"status": "ok"}

STATIC_DIR = os.path.join(os.path.dirname(__file__), "../../frontend/dist")
if os.path.exists(STATIC_DIR):
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
