"""
Linux System Debugging Tool - AutoDebugger API Routes
Executes automated investigations and generates structured diagnostic reports.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import uuid

from ..diagnostics.autodebugger import run_autodebug_investigation
from ..storage.db import StorageService

router = APIRouter(prefix="/api/autodebug", tags=["autodebug"])


class AutoDebugRequest(BaseModel):
    workspace_id: str
    target_name: Optional[str] = "app_debug"
    args: Optional[List[str]] = None
    enable_strace: Optional[bool] = True


@router.post("/run")
def trigger_autodebug(req: AutoDebugRequest):
    ws = StorageService.get_workspace(req.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    result = run_autodebug_investigation(
        workspace_path=ws["path"],
        executable_name=req.target_name or "app_debug",
        args=req.args,
        enable_strace=req.enable_strace if req.enable_strace is not None else True
    )

    # Persist report to SQLite
    report_id = f"rep_{uuid.uuid4().hex[:10]}"
    summary = f"Automated analysis: Verdict {result.get('verdict')}. Found {len(result.get('findings', []))} issues."
    StorageService.save_report(
        report_id=report_id,
        ws_id=req.workspace_id,
        session_id="autodebug",
        title=f"AutoDebug Report: {ws.get('name')}",
        summary=summary,
        findings=result.get("findings", [])
    )
    result["report_id"] = report_id
    return result
