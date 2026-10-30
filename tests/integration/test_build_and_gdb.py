"""
Integration test: Real GCC Compilation & GDB MI Interactive Stepping and Variable Inspection.
"""

from pathlib import Path
import time
from backend.app.workspace.manager import WorkspaceManager
from backend.app.compiler.build_system import compile_project
from backend.app.debugger.session import GdbSession
from backend.app.storage.db import StorageService


def test_build_and_interactive_step():
    # Create a workspace with basic_app template
    ws = WorkspaceManager.create_workspace("GDB Stepping Integration Test", "basic_app")
    ws_path = ws["path"]

    try:
        # Build binary
        build_res = compile_project(ws_path, {"target_name": "app_debug"})
        assert build_res.success is True
        assert build_res.binary_path is not None
        assert Path(build_res.binary_path).is_file()

        # Start GDB Session
        events = []
        sess = GdbSession(
            session_id="test_step_session",
            executable_path=build_res.binary_path,
            working_dir=ws_path,
            event_callback=lambda ev: events.append(ev)
        )

        started = sess.start()
        assert started is True

        # Wait for initial stop at main
        t0 = time.time()
        while sess.state not in ("STOPPED", "TERMINATED", "CRASHED") and (time.time() - t0) < 5.0:
            time.sleep(0.1)

        assert sess.state == "STOPPED"
        assert sess.current_func == "main"
        initial_line = sess.current_line
        assert initial_line is not None

        # Step over
        stepped = sess.step_over()
        assert stepped is True

        # Wait for step to complete and variables to refresh
        t0 = time.time()
        while (time.time() - t0) < 5.0:
            if sess.state == "STOPPED" and sess.current_line != initial_line and len(sess.variables) > 0:
                break
            time.sleep(0.1)

        # Inspect variables
        vars_dict = {v["name"]: v["value"] for v in sess.variables}
        assert "num" in vars_dict

        # Evaluate expression
        eval_res = sess.evaluate_expression("num + 10")
        assert eval_res["success"] is True
        assert eval_res["value"] == "15"

        # Call stack
        assert len(sess.stack_frames) >= 1
        assert sess.stack_frames[0]["func"] == "main"

        # Clean shutdown
        sess.stop()
        assert sess.state == "TERMINATED"

    finally:
        StorageService.delete_workspace(ws["id"])
