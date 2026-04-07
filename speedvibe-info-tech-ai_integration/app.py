"""
Standalone FastAPI app for Speedvibe Info Tech (chat + scrape + voice when merged).

Run from this directory:
  set PYTHONPATH=.
  uvicorn app:app --reload --port 8010

Or:
  uvicorn app:app --reload --port 8010 --app-dir .
"""
import sys
from pathlib import Path

# Ensure `speedvibe_integration` is importable when cwd is this folder
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from speedvibe_integration.router import router as speedvibe_router

app = FastAPI(
    title="Speedvibe Info Tech AI",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(speedvibe_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "speedvibe-integration"}
