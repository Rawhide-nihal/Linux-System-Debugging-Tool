"""
Linux System Debugging Tool - FastAPI Application Entrypoint
Serves REST APIs, WebSocket channels, and optionally static frontend assets.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .debugger.session_manager import SessionManager
from .api.workspace_routes import router as workspace_router
from .api.compiler_routes import router as compiler_router
from .api.analysis_routes import router as analysis_router
from .api.debug_routes import router as debug_router
from .api.autodebug_routes import router as autodebug_router
from .api.test_routes import router as test_router
from .api.report_routes import router as report_router
from .api.settings_routes import router as settings_router
from .api.websocket_routes import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown: clean up any orphaned debug sessions
    SessionManager.cleanup_all()


app = FastAPI(
    title="Linux System Debugging Tool",
    description="Interactive source-level debugger, compiler diagnostics, and forensic crash analyzer.",
    version="3.0.0",
    lifespan=lifespan
)

# CORS configuration for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(workspace_router)
app.include_router(compiler_router)
app.include_router(analysis_router)
app.include_router(debug_router)
app.include_router(autodebug_router)
app.include_router(test_router)
app.include_router(report_router)
app.include_router(settings_router)
app.include_router(ws_router)


# Mount static production frontend if built
dist_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if dist_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
