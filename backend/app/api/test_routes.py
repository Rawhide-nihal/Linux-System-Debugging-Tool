"""
Linux System Debugging Tool - Test Cases API Routes
Creates, manages, and executes test cases to verify logic bugs and validate fixes.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from pathlib import Path
import uuid

from ..verification.test_runner import run_test_case
from ..verification.fix_verifier import verify_bug_fix
from ..storage.db import StorageService

router = APIRouter(prefix="/api/tests", tags=["tests"])


class CreateTestCaseRequest(BaseModel):
    workspace_id: str
    name: str
    args: Optional[List[str]] = None
    stdin_data: Optional[str] = ""
    expected_output: Optional[str] = ""
    expected_exit_code: Optional[int] = 0


class RunTestRequest(BaseModel):
    target_name: Optional[str] = "app_debug"


@router.get("/{ws_id}")
def list_workspace_tests(ws_id: str):
    return StorageService.list_test_cases(ws_id)


@router.post("/")
def create_test_case(req: CreateTestCaseRequest):
    tc_id = f"tc_{uuid.uuid4().hex[:8]}"
    StorageService.save_test_case(
        tc_id=tc_id,
        ws_id=req.workspace_id,
        name=req.name,
        args=req.args or [],
        stdin_data=req.stdin_data or "",
        expected_output=req.expected_output or "",
        expected_exit_code=req.expected_exit_code if req.expected_exit_code is not None else 0
    )
    return {"id": tc_id, "success": True}


@router.delete("/{tc_id}")
def delete_test_case(tc_id: str):
    StorageService.delete_test_case(tc_id)
    return {"success": True}


@router.post("/{tc_id}/run")
def execute_test(tc_id: str, req: RunTestRequest):
    # Find test case
    conn = StorageService.list_workspaces()
    tc = None
    for ws in conn:
        tests = StorageService.list_test_cases(ws["id"])
        for t in tests:
            if t["id"] == tc_id:
                tc = t
                ws_info = ws
                break
        if tc:
            break

    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")

    exe_path = str(Path(ws_info["path"]) / (req.target_name or "app_debug"))
    prev_run = tc.get("last_run")

    run_res = run_test_case(
        executable_path=exe_path,
        args=tc.get("args", []),
        stdin_data=tc.get("stdin_data", ""),
        expected_output=tc.get("expected_output", ""),
        expected_exit_code=tc.get("expected_exit_code", 0),
        working_dir=ws_info["path"]
    )

    # Verification comparison if previous run exists
    verification = None
    if prev_run:
        verification = verify_bug_fix(prev_run, run_res)
        run_res["verification"] = verification

    StorageService.update_test_case_run(tc_id, run_res)
    return run_res
