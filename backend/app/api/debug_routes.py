"""
Linux System Debugging Tool - Interactive Debugger API Routes
Controls GDB execution, breakpoints, stepping, stack navigation, and memory reads.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from pathlib import Path

from ..debugger.session_manager import SessionManager
from ..storage.db import StorageService

router = APIRouter(prefix="/api/debugger", tags=["debugger"])


class CreateSessionRequest(BaseModel):
    workspace_id: str
    executable_name: Optional[str] = "app_debug"


class StartSessionRequest(BaseModel):
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None


class BreakpointRequest(BaseModel):
    file: str
    line: int
    condition: Optional[str] = None


class RunToCursorRequest(BaseModel):
    file: str
    line: int


class EvaluateRequest(BaseModel):
    expression: str


class MemoryReadRequest(BaseModel):
    address: str
    count: Optional[int] = 64


class StdinRequest(BaseModel):
    input_text: str


@router.post("/sessions")
def create_debug_session(req: CreateSessionRequest):
    ws = StorageService.get_workspace(req.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    exe_path = str(Path(ws["path"]) / (req.executable_name or "app_debug"))
    sess = SessionManager.create_session(
        workspace_id=req.workspace_id,
        executable_path=exe_path,
        working_dir=ws["path"]
    )
    return sess.get_snapshot()


@router.get("/sessions/{session_id}")
def get_session_snapshot(session_id: str):
    sess = SessionManager.get_session(session_id)
    if not sess:
        # Check SQLite if already terminated
        saved = StorageService.get_session(session_id)
        if saved:
            return saved
        raise HTTPException(status_code=404, detail="Debug session not found")
    return sess.get_snapshot()


@router.post("/sessions/{session_id}/start")
def start_debugging(session_id: str, req: StartSessionRequest):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.start(args=req.args, env=req.env)
    return {"success": ok, "snapshot": sess.get_snapshot()}


@router.post("/sessions/{session_id}/step-over")
def step_over(session_id: str):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.step_over()
    return {"success": ok}


@router.post("/sessions/{session_id}/step-into")
def step_into(session_id: str):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.step_into()
    return {"success": ok}


@router.post("/sessions/{session_id}/step-out")
def step_out(session_id: str):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.step_out()
    return {"success": ok}


@router.post("/sessions/{session_id}/continue")
def continue_execution(session_id: str):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.continue_exec()
    return {"success": ok}


@router.post("/sessions/{session_id}/pause")
def pause_execution(session_id: str):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.pause()
    return {"success": ok}


@router.post("/sessions/{session_id}/run-to-cursor")
def run_to_cursor(session_id: str, req: RunToCursorRequest):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.run_to_cursor(req.file, req.line)
    return {"success": ok}


@router.post("/sessions/{session_id}/breakpoints")
def add_breakpoint(session_id: str, req: BreakpointRequest):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    bp = sess.set_breakpoint(req.file, req.line, req.condition)
    if not bp:
        raise HTTPException(status_code=400, detail="Failed to set breakpoint in GDB")
    return bp


@router.delete("/sessions/{session_id}/breakpoints/{bp_id}")
def delete_breakpoint(session_id: str, bp_id: int):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.remove_breakpoint(bp_id)
    return {"success": ok}


@router.post("/sessions/{session_id}/frames/{level}")
def select_frame(session_id: str, level: int):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.select_stack_frame(level)
    return {"success": ok, "snapshot": sess.get_snapshot()}


@router.post("/sessions/{session_id}/evaluate")
def evaluate_expression(session_id: str, req: EvaluateRequest):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess.evaluate_expression(req.expression)


@router.post("/sessions/{session_id}/memory")
def read_memory(session_id: str, req: MemoryReadRequest):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess.read_memory(req.address, req.count or 64)


@router.post("/sessions/{session_id}/stdin")
def send_stdin(session_id: str, req: StdinRequest):
    sess = SessionManager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    ok = sess.send_stdin(req.input_text)
    return {"success": ok}


@router.post("/sessions/{session_id}/terminate")
def terminate_session(session_id: str):
    SessionManager.terminate_session(session_id)
    return {"success": True}
