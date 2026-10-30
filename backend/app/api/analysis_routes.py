"""
Linux System Debugging Tool - Static Analysis API Routes
Runs GCC -fanalyzer checks and returns structured problems.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..analysis.static_analyzer import run_static_analysis
from ..storage.db import StorageService

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class StaticAnalysisRequest(BaseModel):
    workspace_id: str
    target_file: Optional[str] = ""


@router.post("/run")
def trigger_static_analysis(req: StaticAnalysisRequest):
    ws = StorageService.get_workspace(req.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    findings = run_static_analysis(ws["path"], req.target_file or "")
    return {
        "workspace_id": req.workspace_id,
        "total_findings": len(findings),
        "findings": findings
    }
