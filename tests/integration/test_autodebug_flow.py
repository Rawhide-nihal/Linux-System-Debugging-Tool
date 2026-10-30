"""
Integration test: End-to-end AutoDebugger Automated Multi-Stage Investigation.
"""

from backend.app.workspace.manager import WorkspaceManager
from backend.app.diagnostics.autodebugger import run_autodebug_investigation
from backend.app.storage.db import StorageService


def test_autodebug_workflow():
    ws = WorkspaceManager.create_workspace("AutoDebug Flow Test", "segfault_repro")
    ws_path = ws["path"]

    try:
        res = run_autodebug_investigation(
            workspace_path=ws_path,
            executable_name="app_debug",
            enable_strace=True
        )

        assert res["success"] is True
        assert res["verdict"] in ("CRITICAL_ISSUES_FOUND", "WARNINGS_FOUND")
        assert len(res["stages"]) >= 4

        # Verify crash was discovered and categorized
        crashes = [f for f in res["findings"] if f["category"] == "RUNTIME_CRASH"]
        assert len(crashes) >= 1
        assert "SIGSEGV" in crashes[0]["title"]

    finally:
        StorageService.delete_workspace(ws["id"])
