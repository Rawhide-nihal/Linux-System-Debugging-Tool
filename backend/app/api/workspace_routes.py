"""
Linux System Debugging Tool - Workspace API Routes
Endpoints for project management, directory tree, file CRUD, search, and zip import.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import tempfile
import shutil

from ..workspace.manager import WorkspaceManager, TEMPLATES
from ..analysis.project_scanner import scan_workspace_tree
from ..storage.db import StorageService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str
    template: Optional[str] = "basic_app"


class FileContentRequest(BaseModel):
    path: str
    content: str


class SearchQueryRequest(BaseModel):
    query: str


@router.get("/")
def list_workspaces():
    return StorageService.list_workspaces()


@router.get("/templates")
def list_templates():
    return [{"id": k, "name": v["name"]} for k, v in TEMPLATES.items()]


@router.post("/")
def create_workspace(req: CreateWorkspaceRequest):
    return WorkspaceManager.create_workspace(req.name, req.template)


@router.get("/{ws_id}")
def get_workspace(ws_id: str):
    ws = StorageService.get_workspace(ws_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws["tree"] = scan_workspace_tree(ws["path"])
    return ws


@router.delete("/{ws_id}")
def delete_workspace(ws_id: str):
    ws = StorageService.get_workspace(ws_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    StorageService.delete_workspace(ws_id)
    try:
        shutil.rmtree(ws["path"])
    except Exception:
        pass
    return {"success": True}


@router.get("/{ws_id}/file")
def read_workspace_file(ws_id: str, path: str):
    ws = StorageService.get_workspace(ws_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    content = WorkspaceManager.read_file(ws["path"], path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"path": path, "content": content}


@router.post("/{ws_id}/file")
def write_workspace_file(ws_id: str, req: FileContentRequest):
    ws = StorageService.get_workspace(ws_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ok = WorkspaceManager.write_file(ws["path"], req.path, req.content)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to write file or path traversal detected")
    return {"success": True, "path": req.path}


@router.delete("/{ws_id}/file")
def delete_workspace_file(ws_id: str, path: str):
    ws = StorageService.get_workspace(ws_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ok = WorkspaceManager.delete_entry(ws["path"], path)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to delete entry")
    return {"success": True}


@router.post("/{ws_id}/search")
def search_workspace(ws_id: str, req: SearchQueryRequest):
    ws = StorageService.get_workspace(ws_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    results = WorkspaceManager.search_text(ws["path"], req.query)
    return {"query": req.query, "results": results}


@router.post("/import-zip")
async def import_workspace_zip(file: UploadFile = File(...), name: str = Form(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        ws_info = WorkspaceManager.import_zip(tmp_path, name)
        return ws_info
    finally:
        try:
            shutil.rmtree(tmp_path, ignore_errors=True)
        except Exception:
            pass
