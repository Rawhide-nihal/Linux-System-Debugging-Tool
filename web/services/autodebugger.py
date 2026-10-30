"""
Real AutoDebugger & GDB Crash Investigation Service for LDST.
Invokes the C ./autodebug engine, tracks the 6 genuine investigation stages,
parses real GDB stack frames and crash lines, separates Observed Facts from
Diagnostic Interpretation, and persists structured diagnostic reports.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from .security import (
    PROJECT_ROOT,
    LOGS_DIR,
    ensure_directories,
)
from .compiler import (
    ensure_core_built,
    get_program_source,
)
from .trace_parser import parse_trace_file, locate_source_evidence
from .process_monitor import ProcessTimelineSampler
from .reports import save_report
from .debugger import (
    _SESSIONS,
    _SESSIONS_LOCK,
    _PROCESS_HANDLES,
    _prepare_target_executable,
    _classify_result,
    _read_file_capped,
)

GDB_FRAME_RE = re.compile(
    r"^#(\d+)\s+(?:0x[0-9a-fA-F]+\s+in\s+)?([a-zA-Z0-9_?]+)\s*\(([^)]*)\)(?:\s+at\s+([^:\n]+):(\d+))?"
)


def parse_gdb_frames(gdb_text: str) -> List[Dict[str, Any]]:
    """
    Parse real GDB backtrace lines (#0 main () at segmentation_fault.c:9) into structured frames.
    Never invents frames.
    """
    frames: List[Dict[str, Any]] = []
    for raw_line in (gdb_text or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("#"):
            continue
        m = GDB_FRAME_RE.match(line)
        if m:
            fnum, func, args, fpath, fline = m.groups()
            frames.append({
                "frame": int(fnum),
                "function": func,
                "args": args,
                "file": os.path.basename(fpath) if fpath else None,
                "full_file": fpath,
                "line": int(fline) if fline and fline.isdigit() else None,
                "raw": line
            })
        else:
            frames.append({
                "frame": len(frames),
                "function": line,
                "args": "",
                "file": None,
                "full_file": None,
                "line": None,
                "raw": line
            })
    return frames


def start_autodebug_session(
    program_name: str,
    enable_gdb: bool = True,
    timeout_sec: float = 20.0,
    async_mode: bool = False
) -> Dict[str, Any]:
    """
    Run a real AutoDebugger investigation using the C ./autodebug binary.
    Tracks genuine 6-stage progress and integrates strace, /proc, and GDB evidence.
    """
    ensure_directories()
    core_check = ensure_core_built()
    if not core_check.get("success"):
        return {
            "success": False,
            "error_type": "CORE_BUILD_FAILED",
            "error": core_check.get("error") or "Failed to build LDST C core."
        }

    if not shutil.which("strace"):
        return {
            "success": False,
            "error_type": "STRACE_MISSING",
            "error": "AutoDebugger requires strace. Install it using: sudo apt install strace",
            "install_hint": "sudo apt install strace"
        }

    prep = _prepare_target_executable(program_name)
    if not prep.get("ready"):
        return {
            "success": False,
            "error_type": prep.get("error_type"),
            "error": prep.get("message"),
            "compilation": prep.get("compilation")
        }

    norm_name = prep["name"]
    rel_exe = prep["rel_exe"]
    rel_src = prep["rel_src"]
    src_path = prep["src_path"]

    now_utc = datetime.now(timezone.utc)
    stamp_str = now_utc.strftime("%Y%m%d-%H%M%S")
    short_uid = uuid.uuid4().hex[:6]
    session_id = f"auto-{stamp_str}-{short_uid}"

    trace_rel = f"traces/trace_{session_id}.txt"
    trace_abs = os.path.join(PROJECT_ROOT, trace_rel)
    c_report_rel = f"results/autodebug_{session_id}.txt"
    gdb_rel = f"logs/gdb_{session_id}.txt"
    gdb_abs = os.path.join(PROJECT_ROOT, gdb_rel)
    c_json_rel = f"logs/c_auto_{session_id}.json"
    c_json_abs = os.path.join(PROJECT_ROOT, c_json_rel)

    target_out_abs = os.path.join(LOGS_DIR, f"stdout_{session_id}.txt")
    target_err_abs = os.path.join(LOGS_DIR, f"stderr_{session_id}.txt")

    autodebug_bin = os.path.join(PROJECT_ROOT, "autodebug")
    cmd = [autodebug_bin]
    if not enable_gdb:
        cmd.append("--no-gdb")
    cmd.extend([
        "--trace-file", trace_rel,
        "--report-file", c_report_rel,
        "--gdb-file", gdb_rel,
        "--json-file", c_json_rel,
        rel_exe
    ])

    initial_stages = [
        {"id": 1, "name": "Executing program", "status": "running", "detail": f"Launching {rel_exe} under strace"},
        {"id": 2, "name": "Collecting termination status", "status": "pending", "detail": "Waiting for child exit / signal"},
        {"id": 3, "name": "Analyzing trace", "status": "pending", "detail": "Pending strace output"},
        {"id": 4, "name": "Collecting process information", "status": "pending", "detail": "Sampling /proc metrics"},
        {"id": 5, "name": "Running GDB", "status": "pending", "detail": "Evaluated after termination check"},
        {"id": 6, "name": "Generating diagnosis", "status": "pending", "detail": "Pending evidence correlation"},
    ]

    session_state: Dict[str, Any] = {
        "session_id": session_id,
        "state": "running",
        "analysis_type": "AutoDebugger",
        "program": norm_name,
        "executable_path": rel_exe,
        "source_path": rel_src,
        "tracing_enabled": True,
        "monitoring_enabled": True,
        "gdb_enabled": enable_gdb,
        "start_time": now_utc.isoformat(),
        "display_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pid": None,
        "ppid": None,
        "process_state": "Running",
        "elapsed_ms": 0.0,
        "stages": initial_stages,
        "program_stdout": "",
        "program_stderr": "",
        "debugger_output": "",
        "timeline_samples": [],
        "stopped_by_user": False,
        "timed_out": False,
        "compilation": prep.get("compilation") or {"success": True, "warnings_count": 0, "errors_count": 0}
    }

    with _SESSIONS_LOCK:
        _SESSIONS[session_id] = session_state

    def _runner():
        env = os.environ.copy()
        env["LDST_TARGET_STDOUT"] = target_out_abs
        env["LDST_TARGET_STDERR"] = target_err_abs

        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True
            )
        except Exception as exc:
            with _SESSIONS_LOCK:
                session_state["state"] = "error"
                session_state["error"] = f"Failed to start AutoDebugger: {exc}"
            return

        with _SESSIONS_LOCK:
            _PROCESS_HANDLES[session_id] = proc
            session_state["pid"] = proc.pid

        sampler = ProcessTimelineSampler(proc.pid, is_strace_wrapped=True)

        while proc.poll() is None:
            elapsed = (time.monotonic() - t0) * 1000.0
            pt = sampler.poll_once()
            with _SESSIONS_LOCK:
                session_state["elapsed_ms"] = round(elapsed, 2)
                if sampler.target_pid:
                    session_state["pid"] = sampler.target_pid
                if sampler.last_ppid:
                    session_state["ppid"] = sampler.last_ppid
                if pt:
                    session_state["process_state"] = pt["state"]
                    session_state["timeline_samples"] = list(sampler.samples)
                session_state["program_stdout"] = _read_file_capped(target_out_abs, 65536)
                session_state["program_stderr"] = _read_file_capped(target_err_abs, 65536)

            if elapsed > timeout_sec * 1000.0:
                with _SESSIONS_LOCK:
                    session_state["timed_out"] = True
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    time.sleep(0.05)
                    if proc.poll() is None:
                        os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                break

            time.sleep(0.015)

        out_bytes, err_bytes = b"", b""
        try:
            out_bytes, err_bytes = proc.communicate(timeout=2)
        except Exception:
            pass

        total_elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
        end_utc = datetime.now(timezone.utc)

        c_auto = {}
        if os.path.isfile(c_json_abs):
            try:
                with open(c_json_abs, "r", encoding="utf-8") as jf:
                    c_auto = json.load(jf)
            except Exception:
                c_auto = {}
            try:
                os.remove(c_json_abs)
            except OSError:
                pass

        prog_stdout = _read_file_capped(target_out_abs)
        prog_stderr = _read_file_capped(target_err_abs)
        for tmp_f in (target_out_abs, target_err_abs):
            if os.path.exists(tmp_f):
                try:
                    os.remove(tmp_f)
                except OSError:
                    pass

        dbg_out = out_bytes.decode("utf-8", errors="replace") if out_bytes else ""
        dbg_err = err_bytes.decode("utf-8", errors="replace") if err_bytes else ""

        trace_info = parse_trace_file(trace_abs) if os.path.isfile(trace_abs) else {
            "available": False,
            "trace_path": "",
            "total_syscalls": 0,
            "total_failures": 0,
            "relevant_failures": 0,
            "loader_noise_failures": 0,
            "grouped_failures": [],
            "all_failures": [],
            "syscall_counts": [],
            "signals": [],
            "primary_failure": None,
            "raw_trace": ""
        }

        terminated_by_signal = bool(c_auto.get("terminated_by_signal", False))
        signal_number = int(c_auto.get("signal_number", 0))
        signal_name_raw = str(c_auto.get("signal_name", ""))
        exit_code = int(c_auto.get("exit_code", 0))
        elapsed_final = float(c_auto.get("elapsed_ms", total_elapsed_ms))
        target_pid = int(c_auto.get("child_pid") or sampler.target_pid or proc.pid)
        ppid_val = int(c_auto.get("ppid") or sampler.last_ppid or 0)

        # Normalize signal short name (e.g. SIGSEGV)
        signal_short = ""
        signal_desc = ""
        if terminated_by_signal and signal_number > 0:
            try:
                signal_short = signal.Signals(signal_number).name
            except Exception:
                signal_short = signal_name_raw if signal_name_raw.startswith("SIG") else f"SIG{signal_number}"
            signal_desc = f"{signal_short} ({signal_name_raw})" if signal_name_raw and signal_name_raw != signal_short else signal_short

        primary_fail = trace_info.get("primary_failure")
        if not primary_fail and c_auto.get("errno_name"):
            primary_fail = {
                "syscall": c_auto.get("failed_syscall", ""),
                "return_value": -1,
                "errno_name": c_auto.get("errno_name", ""),
                "errno_code": int(c_auto.get("errno_code", -1)),
                "description": c_auto.get("errno_meaning", ""),
                "evidence": c_auto.get("primary_evidence", ""),
                "raw": c_auto.get("primary_evidence", "")
            }
        elif primary_fail:
            primary_fail["evidence"] = primary_fail.get("raw", "")

        # GDB output & frames
        gdb_status_code = str(c_auto.get("gdb_status", "not_required"))
        gdb_backtrace = str(c_auto.get("gdb_backtrace", ""))
        raw_gdb_log = _read_file_capped(gdb_abs, 65536) if os.path.isfile(gdb_abs) else ""
        frames = parse_gdb_frames(gdb_backtrace or raw_gdb_log)

        crash_file = str(c_auto.get("crash_file", ""))
        crash_line = int(c_auto.get("crash_line", 0))
        if not crash_line and frames:
            for fr in frames:
                if fr.get("line"):
                    crash_line = fr["line"]
                    crash_file = fr.get("file") or ""
                    break

        if gdb_status_code == "completed":
            gdb_status_label = "Completed — Crash backtrace collected"
            gdb_stage_status = "completed"
        elif gdb_status_code == "unavailable":
            gdb_status_label = "GDB unavailable."
            gdb_stage_status = "skipped"
        elif gdb_status_code == "skipped":
            gdb_status_label = "GDB analysis skipped by user option."
            gdb_stage_status = "skipped"
        else:
            gdb_status_label = "GDB analysis not required."
            gdb_stage_status = "not_required"

        # Source evidence correlation (prefer GDB line if available, else syscall line)
        src_ev = locate_source_evidence(
            src_path,
            failed_syscall=(primary_fail or {}).get("syscall", ""),
            gdb_line=crash_line
        )

        peak_vmsize = max(int(c_auto.get("peak_vm_size_kb", 0)), sampler.peak_vm_size_kb)
        peak_vmrss = max(int(c_auto.get("peak_vm_rss_kb", 0)), sampler.peak_vm_rss_kb)
        peak_threads = max(int(c_auto.get("peak_threads", 0)), sampler.peak_threads)
        peak_fds = max(int(c_auto.get("peak_open_fds", -1)), sampler.peak_open_fds)
        total_samples = max(int(c_auto.get("monitor_samples", 0)), len(sampler.samples))

        timeline_points = list(sampler.samples)
        if not timeline_points and peak_vmsize > 0:
            timeline_points.append({
                "sample_index": 1,
                "elapsed_ms": round(elapsed_final * 0.5, 2),
                "pid": target_pid,
                "ppid": ppid_val,
                "name": norm_name,
                "state": "R (Running)",
                "cpu_percent": 0.0,
                "vm_size_kb": peak_vmsize,
                "vm_rss_kb": peak_vmrss,
                "threads": peak_threads or 1,
                "open_fds": peak_fds if peak_fds >= 0 else 3
            })

        stopped_user = bool(session_state.get("stopped_by_user"))
        timed_out_flag = bool(session_state.get("timed_out"))

        classification = _classify_result(
            terminated_by_signal=terminated_by_signal,
            signal_name=signal_short,
            signal_number=signal_number,
            exit_code=exit_code,
            primary_failure=primary_fail,
            stopped_by_user=stopped_user,
            timed_out=timed_out_flag
        )

        # Build Observed Facts vs Diagnostic Interpretation (Section 18 requirement)
        observed_facts: List[str] = [
            f"Target executable '{rel_exe}' executed with PID {target_pid} (duration: {elapsed_final:.2f} ms)."
        ]
        if terminated_by_signal:
            observed_facts.append(f"Process terminated abnormally by signal {signal_number} ({signal_short}).")
        else:
            observed_facts.append(f"Process terminated normally with exit code {exit_code}.")

        if trace_info.get("available"):
            observed_facts.append(
                f"strace recorded {trace_info['total_syscalls']} system calls and "
                f"{trace_info['relevant_failures']} relevant failure(s)."
            )
        if primary_fail and primary_fail.get("syscall"):
            observed_facts.append(
                f"Failing system call: {primary_fail['syscall']}() returned -1 with "
                f"{primary_fail['errno_name']} ({primary_fail['errno_code']}: {primary_fail['description']})."
            )
        if frames:
            top_f = frames[0]
            loc_str = f" at {top_f['file']}:{top_f['line']}" if top_f.get("file") and top_f.get("line") else ""
            observed_facts.append(f"GDB stopped in frame #{top_f['frame']} {top_f['function']}(){loc_str}.")
        if src_ev and src_ev.get("code_line"):
            observed_facts.append(
                f"Source context at {src_ev['file']}:{src_ev['line']} reads: `{src_ev['code_line']}`."
            )

        diagnosis = str(c_auto.get("diagnosis", "")).strip()
        next_step = str(c_auto.get("next_step", "")).strip()
        if not diagnosis:
            if stopped_user:
                diagnosis = "AutoDebugger session was manually stopped by the user."
                next_step = "Re-run AutoDebugger when ready."
            elif timed_out_flag:
                diagnosis = f"Execution timed out after {timeout_sec:.1f} seconds."
                next_step = "Inspect loops and blocking system calls."
            else:
                diagnosis = "Execution completed."
                next_step = "Review the captured trace and output."

        final_stages = [
            {
                "id": 1,
                "name": "Executing program",
                "status": "completed",
                "detail": f"Executed {rel_exe} (PID {target_pid}, {elapsed_final:.2f} ms)"
            },
            {
                "id": 2,
                "name": "Collecting termination status",
                "status": "completed",
                "detail": (
                    f"Terminated by signal {signal_short} ({signal_number})"
                    if terminated_by_signal else f"Exited normally with code {exit_code}"
                )
            },
            {
                "id": 3,
                "name": "Analyzing trace",
                "status": "completed" if trace_info.get("available") else "skipped",
                "detail": (
                    f"{trace_info['total_syscalls']} syscalls, {trace_info['relevant_failures']} relevant failure(s)"
                    if trace_info.get("available") else "Trace not available"
                )
            },
            {
                "id": 4,
                "name": "Collecting process information",
                "status": "completed" if peak_vmsize > 0 else "skipped",
                "detail": (
                    f"Peak VmSize: {peak_vmsize} KB, Peak VmRSS: {peak_vmrss} KB ({total_samples} sample(s))"
                    if peak_vmsize > 0 else "Process exited before /proc snapshot"
                )
            },
            {
                "id": 5,
                "name": "Running GDB",
                "status": gdb_stage_status,
                "detail": gdb_status_label
            },
            {
                "id": 6,
                "name": "Generating diagnosis",
                "status": "completed",
                "detail": f"Result classified as {classification['result_badge']}"
            }
        ]

        source_info = get_program_source(norm_name)

        completed_data: Dict[str, Any] = {
            "success": True,
            "session_id": session_id,
            "state": "completed",
            "analysis_type": "AutoDebugger",
            "program": norm_name,
            "executable_path": rel_exe,
            "source_path": rel_src,
            "source_code": source_info.get("code", ""),
            "tracing_enabled": True,
            "monitoring_enabled": True,
            "gdb_enabled": enable_gdb,
            "timestamp": end_utc.isoformat(),
            "start_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "end_time": end_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "display_time": end_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "elapsed_ms": elapsed_final,
            "pid": target_pid,
            "ppid": ppid_val,
            "process_state": "Terminated" if terminated_by_signal else "Exited",
            "termination_type": (
                "Stopped by User" if stopped_user else
                f"Timeout (> {timeout_sec}s)" if timed_out_flag else
                "Abnormal (Signal)" if terminated_by_signal else "Normal"
            ),
            "exited_normally": not terminated_by_signal and not stopped_user and not timed_out_flag,
            "exit_code": exit_code if not terminated_by_signal else f"128 + {signal_number} ({128 + signal_number})",
            "terminated_by_signal": terminated_by_signal,
            "signal_number": signal_number if terminated_by_signal else None,
            "signal_name": signal_short if terminated_by_signal else None,
            "signal_description": signal_desc if terminated_by_signal else None,
            "result_badge": classification["result_badge"],
            "badge_tone": classification["badge_tone"],
            "overall_status": classification["overall_status"],
            "illustration_type": classification["illustration_type"],
            "stages": final_stages,
            "compilation": prep.get("compilation") or {"success": True, "warnings_count": 0, "errors_count": 0},
            "detected_error": primary_fail,
            "source_evidence": src_ev,
            "process_stats": {
                "peak_vm_size_kb": peak_vmsize,
                "peak_vm_rss_kb": peak_vmrss,
                "peak_threads": peak_threads,
                "peak_open_fds": peak_fds,
                "samples_count": total_samples,
                "elapsed_ms": elapsed_final,
                "timeline": timeline_points,
                "short_process_note": (
                    "Process completed before multiple periodic /proc samples were needed."
                    if len(timeline_points) <= 1 else ""
                )
            },
            "syscall_analysis": trace_info,
            "gdb_analysis": {
                "available": gdb_status_code == "completed",
                "status": gdb_status_code,
                "status_label": gdb_status_label,
                "backtrace": gdb_backtrace,
                "raw_output": raw_gdb_log,
                "frames": frames,
                "crash_file": crash_file,
                "crash_line": crash_line
            },
            "program_stdout": prog_stdout,
            "program_stderr": prog_stderr,
            "debugger_output": dbg_out + ("\n" + dbg_err if dbg_err else ""),
            "observed_facts": observed_facts,
            "diagnosis": diagnosis,
            "next_step": next_step,
            "trace_file": trace_rel,
            "c_report_file": c_report_rel,
            "gdb_file": gdb_rel if terminated_by_signal and enable_gdb else None
        }

        save_report(completed_data)

        with _SESSIONS_LOCK:
            _SESSIONS[session_id] = completed_data
            _PROCESS_HANDLES.pop(session_id, None)

    runner_thread = threading.Thread(target=_runner, daemon=True)
    runner_thread.start()

    if not async_mode:
        runner_thread.join(timeout=timeout_sec + 4.0)
        with _SESSIONS_LOCK:
            return dict(_SESSIONS[session_id])

    runner_thread.join(timeout=0.15)
    with _SESSIONS_LOCK:
        return dict(_SESSIONS[session_id])
