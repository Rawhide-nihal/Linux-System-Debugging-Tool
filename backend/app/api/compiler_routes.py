"""
Linux System Debugging Tool - Compiler API Routes
Builds C projects and serves structured diagnostics.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from ..compiler.build_system import compile_project
from ..storage.db import StorageService

router = APIRouter(prefix="/api/compiler", tags=["compiler"])


class BuildRequest(BaseModel):
    workspace_id: str
    target_name: Optional[str] = "app_debug"
    cflags: Optional[list] = None
    build_mode: Optional[str] = "auto"
    selected_file: Optional[str] = None


@router.post("/build")
def trigger_build(req: BuildRequest):
    ws = StorageService.get_workspace(req.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    cfg = ws.get("config", {})
    if req.cflags:
        cfg["cflags"] = req.cflags
    if req.target_name:
        cfg["target_name"] = req.target_name
    if req.build_mode:
        cfg["build_mode"] = req.build_mode
    if req.selected_file:
        cfg["selected_file"] = req.selected_file

    res = compile_project(ws["path"], cfg)
    return res.to_dict()
