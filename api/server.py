from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.routes import router

app = FastAPI(title="git-impact-analyzer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

_FRONTEND = Path(__file__).parent.parent / "dashboard" / "frontend" / "index.html"


@app.get("/")
def serve_dashboard() -> FileResponse:
    return FileResponse(str(_FRONTEND))
