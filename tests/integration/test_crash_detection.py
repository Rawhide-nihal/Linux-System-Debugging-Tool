"""
Integration test: Real SIGSEGV Crash Trapping and Forensic Root-Cause Diagnosis.
"""

from pathlib import Path
import time
from backend.app.workspace.manager import WorkspaceManager
from backend.app.compiler.build_system import compile_project
from backend.app.debugger.session import GdbSession
from backend.app.diagnostics.crash_investigator import investigate_crash
from backend.app.storage.db import StorageService


def test_real_segfault_trapping():
    # Create workspace with segfault reproducer template
    ws = WorkspaceManager.create_workspace("Segfault Crash Test", "segfault_repro")
    ws_path = ws["path"]

    try:
        build_res = compile_project(ws_path, {"target_name": "app_debug"})
        assert build_res.success is True

        sess = GdbSession(
            session_id="test_crash_session",
            executable_path=build_res.binary_path,
            working_dir=ws_path
        )
        assert sess.start() is True

        # Wait until stopped at main
        t_init = time.time()
        while sess.state not in ("STOPPED", "CRASHED", "TERMINATED") and (time.time() - t_init) < 5.0:
            time.sleep(0.05)

        # Continue directly into the crash
        sess.continue_exec()

        t0 = time.time()
        while sess.state not in ("CRASHED", "TERMINATED") and (time.time() - t0) < 6.0:
            time.sleep(0.1)

        assert sess.stop_signal == "SIGSEGV" or sess.state == "CRASHED"

        # Forensic analysis
        src = (Path(ws_path) / "main.c").read_text()
        inv = investigate_crash(
            signal_name="SIGSEGV",
            stopped_data={
                "file": sess.current_file,
                "line": sess.current_line,
                "func": sess.current_func,
                "variables": sess.variables,
                "call_stack": sess.stack_frames
            },
            source_code=src
        )

        assert inv["category"] == "RUNTIME_CRASH"
        assert "dereference" in inv["likely_cause"].lower() or "segmentation fault" in inv["likely_cause"].lower()
        assert inv["fault_location"]["function"] in ("print_user", "main")

        sess.stop()

    finally:
        StorageService.delete_workspace(ws["id"])
