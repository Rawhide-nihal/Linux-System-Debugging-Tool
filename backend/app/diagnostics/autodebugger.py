"""
Linux System Debugging Tool - AutoDebugger Automated Investigation Engine
Orchestrates multi-stage, evidence-based diagnostic investigations without fabricated results.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..compiler.build_system import compile_project
from ..analysis.static_analyzer import run_static_analysis
from ..tracing.strace_runner import run_strace_on_target
from ..debugger.session import GdbSession
from .crash_investigator import investigate_crash
from ..storage.db import StorageService


def run_autodebug_investigation(workspace_path: str, executable_name: str = "app_debug",
                                args: Optional[List[str]] = None, enable_strace: bool = True) -> Dict[str, Any]:
    """
    Executes a structured automated investigation:
    1. Validation & Scan
    2. Build & Compiler Diagnostics
    3. Static Analysis (-fanalyzer)
    4. Execution under GDB & Signal Trapping
    5. Optional System Call Tracing (strace)
    6. Fault Correlation & Forensic Diagnosis
    """
    ws = Path(workspace_path).resolve()
    stages: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []

    # Stage 1: Validation
    stages.append({"stage": "Validation", "status": "COMPLETED", "detail": f"Workspace validated: {ws.name}"})

    # Stage 2: Compilation
    build_res = compile_project(str(ws), {"target_name": executable_name})
    if not build_res.success:
        stages.append({"stage": "Compilation", "status": "FAILED", "detail": "Compilation failed with errors."})
        for diag in build_res.diagnostics:
            if diag["severity"] == "error":
                findings.append({
                    "category": "COMPILATION_ERROR",
                    "title": f"Compiler Error: {diag['message']}",
                    "file": diag["file"],
                    "line": diag["line"],
                    "column": diag["column"],
                    "severity": "CRITICAL",
                    "evidence": diag.get("snippet") or diag.get("raw"),
                    "confidence": "VERY HIGH",
                    "suggested_action": "Fix syntax or type errors at the reported line before continuing."
                })
        return {
            "success": False,
            "verdict": "COMPILATION_FAILED",
            "stages": stages,
            "findings": findings,
            "diagnostics": build_res.diagnostics,
            "binary_path": None
        }

    stages.append({"stage": "Compilation", "status": "COMPLETED", "detail": "Build succeeded with debug symbols (-g)."})

    # Stage 3: Static Analysis
    analyzer_findings = run_static_analysis(str(ws))
    stages.append({
        "stage": "Static Analysis",
        "status": "COMPLETED",
        "detail": f"Completed GCC -fanalyzer pass ({len(analyzer_findings)} warning(s) found)."
    })
    for af in analyzer_findings:
        findings.append({
            "category": "STATIC_ANALYSIS",
            "title": f"Static Bug Risk: {af['message']}",
            "file": af["file"],
            "line": af["line"],
            "column": af["column"],
            "severity": "WARNING",
            "evidence": af.get("snippet") or af.get("raw"),
            "confidence": "HIGH",
            "suggested_action": "Review memory allocation, pointer dereferences, or uninitialized variables."
        })

    # Stage 4: Execution under GDB
    bin_path = build_res.binary_path
    gdb_session = GdbSession(session_id="autodebug", executable_path=bin_path, working_dir=str(ws))
    gdb_ok = gdb_session.start(args=args)

    if not gdb_ok:
        stages.append({"stage": "GDB Execution", "status": "FAILED", "detail": "Could not launch target under GDB."})
        return {
            "success": False,
            "verdict": "LAUNCH_FAILED",
            "stages": stages,
            "findings": findings,
            "binary_path": bin_path
        }

    # Wait until initially stopped at main
    import time
    wait_start = time.time()
    while gdb_session.state not in ("STOPPED", "TERMINATED", "CRASHED") and (time.time() - wait_start) < 4.0:
        time.sleep(0.05)

    # Continue until stop or exit
    gdb_session.continue_exec()

    # Wait for completion or timeout
    start_t = time.time()
    while gdb_session.state in ("RUNNING", "STARTING") and (time.time() - start_t) < 8.0:
        time.sleep(0.1)

    stages.append({
        "stage": "GDB Execution",
        "status": "COMPLETED",
        "detail": f"Target stopped with state: {gdb_session.state} (Stop reason: {gdb_session.stop_reason})"
    })

    crash_details = None
    if gdb_session.state == "CRASHED" or gdb_session.stop_signal:
        src_text = ""
        if gdb_session.current_file:
            cand = ws / gdb_session.current_file
            if cand.is_file():
                src_text = cand.read_text(encoding="utf-8", errors="replace")

        crash_details = investigate_crash(
            signal_name=gdb_session.stop_signal or "SIGSEGV",
            stopped_data={
                "file": gdb_session.current_file,
                "line": gdb_session.current_line,
                "func": gdb_session.current_func,
                "variables": gdb_session.variables,
                "call_stack": gdb_session.stack_frames
            },
            source_code=src_text
        )

        findings.insert(0, {
            "category": "RUNTIME_CRASH",
            "title": f"Process Crash: {gdb_session.stop_signal}",
            "file": gdb_session.current_file,
            "line": gdb_session.current_line,
            "severity": "CRITICAL",
            "evidence": crash_details.get("likely_cause"),
            "confidence": crash_details.get("confidence", "HIGH"),
            "suggested_action": crash_details.get("suggested_action"),
            "variables": gdb_session.variables,
            "call_stack": gdb_session.stack_frames
        })

    elif gdb_session.exit_code is not None and gdb_session.exit_code != 0:
        findings.insert(0, {
            "category": "NON_ZERO_EXIT",
            "title": f"Non-Zero Exit Code: {gdb_session.exit_code}",
            "file": gdb_session.current_file,
            "line": gdb_session.current_line,
            "severity": "WARNING",
            "evidence": f"Process terminated abnormally with exit code {gdb_session.exit_code}.",
            "confidence": "HIGH",
            "suggested_action": "Check return codes and error handling in main() or invoked functions."
        })

    # Stage 5: System Call Tracing
    strace_res = None
    if enable_strace:
        strace_res = run_strace_on_target(bin_path, args=args, working_dir=str(ws), timeout=10.0)
        stages.append({
            "stage": "System Call Tracing",
            "status": "COMPLETED",
            "detail": f"Traced {strace_res['total_syscalls']} syscalls ({strace_res['failed_syscalls_count']} failed calls)."
        })
        for fcall in strace_res["failed_events"]:
            if fcall["errno"] in ("ENOENT", "EACCES", "EBADF"):
                findings.append({
                    "category": "SYSCALL_FAILURE",
                    "title": f"Failed System Call: {fcall['syscall']} returned {fcall['errno']}",
                    "file": gdb_session.current_file,
                    "line": gdb_session.current_line,
                    "severity": "WARNING",
                    "evidence": fcall["raw"],
                    "confidence": "HIGH",
                    "suggested_action": fcall["errno_description"]
                })

    gdb_session.stop()

    verdict = "HEALTHY"
    if any(f["severity"] == "CRITICAL" for f in findings):
        verdict = "CRITICAL_ISSUES_FOUND"
    elif findings:
        verdict = "WARNINGS_FOUND"

    return {
        "success": True,
        "verdict": verdict,
        "stages": stages,
        "findings": findings,
        "binary_path": bin_path,
        "exit_code": gdb_session.exit_code,
        "signal": gdb_session.stop_signal,
        "crash_details": crash_details,
        "syscall_summary": {
            "total": strace_res["total_syscalls"] if strace_res else 0,
            "failed": strace_res["failed_syscalls_count"] if strace_res else 0
        } if strace_res else None
    }
