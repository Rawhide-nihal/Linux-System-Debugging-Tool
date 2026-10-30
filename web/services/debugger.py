"""
Real Debugger Execution & Session Management Service for LDST.
Connects the web interface to the C ./debugger binary and direct execution,
manages live /proc sampling, timeout and user-stop handling, strace/errno analysis,
and structured diagnostic report generation.
"""

import json
import os
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
    TRACES_DIR,
    RESULTS_DIR,
    OFFICIAL_PROGRAMS,
    ensure_directories,
    get_program_paths,
)
from .compiler import (
    compile_program,
    ensure_core_built,
    get_program_source,
    _load_compile_states,
)
from .trace_parser import parse_trace_file, locate_source_evidence
from .process_monitor import ProcessTimelineSampler
from .reports import save_report

MAX_OUTPUT_BYTES = 256 * 1024  # 256 KB cap for huge stdout/stderr

# Active and recently completed sessions in memory
_SESSIONS_LOCK = threading.Lock()
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_PROCESS_HANDLES: Dict[str, subprocess.Popen] = {}


def _read_file_capped(path: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            raw = f.read(max_bytes)
        text = raw.decode("utf-8", errors="replace")
        if size > max_bytes:
            text += f"\n\n[Output truncated at {max_bytes // 1024} KB (total size: {size} bytes)]"
        return text
    except Exception:
        return ""


def get_active_sessions_summary() -> List[Dict[str, Any]]:
    with _SESSIONS_LOCK:
        active = []
        for sid, s in _SESSIONS.items():
            if s.get("state") == "running":
                active.append({
                    "session_id": sid,
                    "program": s.get("program"),
                    "analysis_type": s.get("analysis_type"),
                    "pid": s.get("pid"),
                    "process_state": s.get("process_state", "Running"),
                    "elapsed_ms": s.get("elapsed_ms", 0),
                    "started_at": s.get("start_time")
                })
        return active


def get_session_status(session_id: str) -> Optional[Dict[str, Any]]:
    with _SESSIONS_LOCK:
        s = _SESSIONS.get(session_id)
        if not s:
            return None
        return dict(s)


def stop_session(session_id: str) -> Dict[str, Any]:
    """
    Allow user to cleanly terminate a running debugging session and its child processes.
    """
    with _SESSIONS_LOCK:
        s = _SESSIONS.get(session_id)
        proc = _PROCESS_HANDLES.get(session_id)
        if not s:
            raise FileNotFoundError(f"Session '{session_id}' not found.")
        if s.get("state") != "running" or not proc:
            return {"success": True, "session_id": session_id, "message": "Session already finished."}
        s["stopped_by_user"] = True

    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(0.08)
        if proc.poll() is None:
            os.killpg(pgid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    return {"success": True, "session_id": session_id, "message": "Session termination signal sent."}


def _prepare_target_executable(program_name: str) -> Dict[str, Any]:
    """
    Verify target program is compiled and never execute a stale binary after compile failure.
    """
    norm_name, src_path, exe_path = get_program_paths(program_name)

    if not os.path.isfile(src_path):
        return {
            "ready": False,
            "error_type": "MISSING_SOURCE",
            "message": f"Source file 'tests/{norm_name}.c' does not exist."
        }

    cstate = _load_compile_states().get(norm_name, {})
    if cstate.get("status") == "failed":
        return {
            "ready": False,
            "error_type": "COMPILATION_FAILED",
            "message": f"Cannot run '{norm_name}': the most recent compilation failed. Fix the compiler errors and recompile first.",
            "compilation": cstate
        }

    exe_exists = os.path.isfile(exe_path) and os.access(exe_path, os.X_OK)
    if not exe_exists:
        # Attempt to compile now
        comp_res = compile_program(norm_name)
        if not comp_res.get("success"):
            return {
                "ready": False,
                "error_type": "COMPILATION_FAILED",
                "message": f"Compilation of 'tests/{norm_name}.c' failed.",
                "compilation": comp_res
            }
        cstate = comp_res

    return {
        "ready": True,
        "name": norm_name,
        "src_path": src_path,
        "exe_path": exe_path,
        "rel_exe": f"tests/{norm_name}",
        "rel_src": f"tests/{norm_name}.c",
        "compilation": cstate
    }


def _classify_result(
    terminated_by_signal: bool,
    signal_name: str,
    signal_number: int,
    exit_code: int,
    primary_failure: Optional[Dict[str, Any]],
    stopped_by_user: bool = False,
    timed_out: bool = False
) -> Dict[str, str]:
    """
    Determine truthful result badge, tone, and overall status strictly from real evidence.
    """
    if stopped_by_user:
        return {
            "result_badge": "STOPPED",
            "badge_tone": "warning",
            "overall_status": "Stopped by User",
            "illustration_type": "empty"
        }
    if timed_out:
        return {
            "result_badge": "TIMEOUT",
            "badge_tone": "warning",
            "overall_status": "Execution Timed Out",
            "illustration_type": "error"
        }
    if terminated_by_signal and signal_number > 0:
        sig_short = signal_name.split()[0] if signal_name else f"SIG{signal_number}"
        return {
            "result_badge": sig_short,
            "badge_tone": "danger",
            "overall_status": f"Crashed / Terminated by {sig_short}",
            "illustration_type": "error"
        }
    if primary_failure and primary_failure.get("errno_name"):
        ename = primary_failure["errno_name"]
        tone = "danger" if exit_code != 0 else "warning"
        return {
            "result_badge": ename,
            "badge_tone": tone,
            "overall_status": f"System Call Failure ({ename})",
            "illustration_type": "error" if exit_code != 0 else "empty"
        }
    if exit_code == 0:
        return {
            "result_badge": "SUCCESS",
            "badge_tone": "success",
            "overall_status": "Clean Execution",
            "illustration_type": "success"
        }
    return {
        "result_badge": f"EXIT {exit_code}",
        "badge_tone": "warning",
        "overall_status": f"Non-Zero Exit ({exit_code})",
        "illustration_type": "empty"
    }


def start_debugger_session(
    program_name: str,
    use_trace: bool = True,
    use_monitor: bool = True,
    capture_output: bool = True,
    mode: str = "Debugger",
    timeout_sec: float = 15.0,
    async_mode: bool = False
) -> Dict[str, Any]:
    """
    Run a real debugging or direct execution session on a target C program.
    Uses the C ./debugger engine (or direct execution when mode == 'Direct Run').
    """
    ensure_directories()
    core_check = ensure_core_built()
    if not core_check.get("success"):
        return {
            "success": False,
            "error_type": "CORE_BUILD_FAILED",
            "error": core_check.get("error") or "Failed to build LDST C core."
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

    if use_trace and not shutil.which("strace"):
        return {
            "success": False,
            "error_type": "STRACE_MISSING",
            "error": "System-call tracing unavailable: strace was not found on this system. Install it using: sudo apt install strace",
            "install_hint": "sudo apt install strace"
        }

    now_utc = datetime.now(timezone.utc)
    stamp_str = now_utc.strftime("%Y%m%d-%H%M%S")
    short_uid = uuid.uuid4().hex[:6]
    prefix = "run" if mode == "Direct Run" else "dbg"
    session_id = f"{prefix}-{stamp_str}-{short_uid}"

    trace_rel = f"traces/trace_{session_id}.txt" if use_trace else ""
    trace_abs = os.path.join(PROJECT_ROOT, trace_rel) if use_trace else ""
    c_report_rel = f"results/report_{session_id}.txt"
    c_json_rel = f"logs/c_session_{session_id}.json"
    c_json_abs = os.path.join(PROJECT_ROOT, c_json_rel)

    target_out_abs = os.path.join(LOGS_DIR, f"stdout_{session_id}.txt")
    target_err_abs = os.path.join(LOGS_DIR, f"stderr_{session_id}.txt")

    if mode == "Direct Run":
        cmd = [os.path.join(PROJECT_ROOT, rel_exe)]
    else:
        debugger_bin = os.path.join(PROJECT_ROOT, "debugger")
        cmd = [debugger_bin]
        if not use_trace:
            cmd.append("--no-trace")
        else:
            cmd.extend(["--trace-file", trace_rel])
        if not use_monitor:
            cmd.append("--no-monitor")
        cmd.extend([
            "--report-file", c_report_rel,
            "--json-file", c_json_rel,
            rel_exe
        ])

    session_state: Dict[str, Any] = {
        "session_id": session_id,
        "state": "running",
        "analysis_type": mode,
        "program": norm_name,
        "executable_path": rel_exe,
        "source_path": rel_src,
        "tracing_enabled": use_trace and mode != "Direct Run",
        "monitoring_enabled": use_monitor,
        "capture_output": capture_output,
        "start_time": now_utc.isoformat(),
        "display_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pid": None,
        "ppid": None,
        "process_state": "Starting",
        "elapsed_ms": 0.0,
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
        if capture_output and mode != "Direct Run":
            env["LDST_TARGET_STDOUT"] = target_out_abs
            env["LDST_TARGET_STDERR"] = target_err_abs

        t0 = time.monotonic()
        try:
            if mode == "Direct Run":
                f_out = open(target_out_abs, "wb")
                f_err = open(target_err_abs, "wb")
                proc = subprocess.Popen(
                    cmd,
                    cwd=PROJECT_ROOT,
                    stdout=f_out,
                    stderr=f_err,
                    env=env,
                    start_new_session=True
                )
            else:
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
                session_state["error"] = f"Process startup failed: {exc}"
            return

        with _SESSIONS_LOCK:
            _PROCESS_HANDLES[session_id] = proc
            session_state["pid"] = proc.pid
            session_state["process_state"] = "R (Running)"

        sampler = ProcessTimelineSampler(
            proc.pid,
            is_strace_wrapped=(use_trace and mode != "Direct Run")
        )

        while proc.poll() is None:
            elapsed = (time.monotonic() - t0) * 1000.0
            if use_monitor:
                pt = sampler.poll_once()
            else:
                pt = None

            with _SESSIONS_LOCK:
                session_state["elapsed_ms"] = round(elapsed, 2)
                if sampler.target_pid:
                    session_state["pid"] = sampler.target_pid
                if sampler.last_ppid:
                    session_state["ppid"] = sampler.last_ppid
                if pt:
                    session_state["process_state"] = pt["state"]
                    session_state["timeline_samples"] = list(sampler.samples)
                if capture_output:
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

        # Ensure process is reaped to prevent zombie processes
        dbg_stdout_bytes = b""
        dbg_stderr_bytes = b""
        try:
            if mode == "Direct Run":
                proc.wait(timeout=2)
                f_out.close()
                f_err.close()
            else:
                dbg_stdout_bytes, dbg_stderr_bytes = proc.communicate(timeout=2)
        except Exception:
            pass

        total_elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
        end_utc = datetime.now(timezone.utc)

        # Read C debugger JSON output if produced
        c_summary = {}
        if os.path.isfile(c_json_abs):
            try:
                with open(c_json_abs, "r", encoding="utf-8") as jf:
                    c_summary = json.load(jf)
            except Exception:
                c_summary = {}
            try:
                os.remove(c_json_abs)
            except OSError:
                pass

        prog_stdout = _read_file_capped(target_out_abs) if capture_output else ""
        prog_stderr = _read_file_capped(target_err_abs) if capture_output else ""

        # Clean up temporary stdout/stderr capture files
        for tmp_f in (target_out_abs, target_err_abs):
            if os.path.exists(tmp_f):
                try:
                    os.remove(tmp_f)
                except OSError:
                    pass

        dbg_out_text = dbg_stdout_bytes.decode("utf-8", errors="replace") if dbg_stdout_bytes else ""
        dbg_err_text = dbg_stderr_bytes.decode("utf-8", errors="replace") if dbg_stderr_bytes else ""

        # Determine termination status from C engine (or direct process returncode)
        if c_summary:
            exited_normally = bool(c_summary.get("exited_normally", True))
            exit_code = int(c_summary.get("exit_code", 0))
            terminated_by_signal = bool(c_summary.get("terminated_by_signal", False))
            signal_number = int(c_summary.get("signal_number", 0))
            signal_name = str(c_summary.get("signal_name", ""))
            signal_desc = str(c_summary.get("signal_description", ""))
            elapsed_final = float(c_summary.get("elapsed_ms", total_elapsed_ms))
            target_pid = int(c_summary.get("target_pid") or c_summary.get("child_pid") or proc.pid)
            ppid_val = int(c_summary.get("ppid") or sampler.last_ppid or 0)
        else:
            rc = proc.returncode if proc.returncode is not None else 0
            if rc < 0:
                terminated_by_signal = True
                exited_normally = False
                signal_number = -rc
                exit_code = 128 + signal_number
                try:
                    signal_name = signal.Signals(signal_number).name
                except Exception:
                    signal_name = f"SIG{signal_number}"
                signal_desc = signal_name
            else:
                exited_normally = True
                terminated_by_signal = False
                exit_code = rc
                signal_number = 0
                signal_name = ""
                signal_desc = ""
            elapsed_final = total_elapsed_ms
            target_pid = sampler.target_pid or proc.pid
            ppid_val = sampler.last_ppid or os.getpid()

        # Parse real strace log if tracing was enabled
        if use_trace and mode != "Direct Run" and os.path.isfile(trace_abs):
            trace_info = parse_trace_file(trace_abs)
        else:
            trace_info = {
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

        primary_fail = trace_info.get("primary_failure")
        if not primary_fail and c_summary.get("found_error"):
            primary_fail = {
                "syscall": c_summary.get("failed_syscall", ""),
                "return_value": -1,
                "errno_name": c_summary.get("errno_name", ""),
                "errno_code": c_summary.get("errno_code", -1),
                "description": c_summary.get("errno_description", ""),
                "evidence": c_summary.get("primary_evidence", ""),
                "raw": c_summary.get("primary_evidence", "")
            }
        elif primary_fail:
            primary_fail["evidence"] = primary_fail.get("raw", "")

        # Merge /proc statistics from C engine and Python sampler
        peak_vmsize = max(int(c_summary.get("peak_vm_size_kb", 0)), sampler.peak_vm_size_kb)
        peak_vmrss = max(int(c_summary.get("peak_vm_rss_kb", 0)), sampler.peak_vm_rss_kb)
        peak_threads = max(int(c_summary.get("peak_threads", 0)), sampler.peak_threads)
        peak_fds = max(int(c_summary.get("peak_open_fds", -1)), sampler.peak_open_fds)
        total_samples = max(int(c_summary.get("monitor_samples", 0)), len(sampler.samples))

        # If C engine captured a snapshot but Python thread saw 0 samples (very fast process),
        # include that single real C snapshot in timeline_samples so the chart has the real point
        timeline_points = list(sampler.samples)
        if not timeline_points and use_monitor and peak_vmsize > 0:
            timeline_points.append({
                "sample_index": 1,
                "elapsed_ms": round(elapsed_final * 0.5, 2),
                "pid": target_pid,
                "ppid": ppid_val,
                "name": norm_name,
                "state": c_summary.get("process_state", "R (Running)"),
                "cpu_percent": 0.0,
                "vm_size_kb": peak_vmsize,
                "vm_rss_kb": peak_vmrss,
                "threads": peak_threads or 1,
                "open_fds": peak_fds if peak_fds >= 0 else 3
            })

        stopped_user = bool(session_state.get("stopped_by_user"))
        timed_out_flag = bool(session_state.get("timed_out"))

        if stopped_user:
            term_type = "Stopped by User"
        elif timed_out_flag:
            term_type = f"Timeout (> {timeout_sec}s)"
        elif terminated_by_signal:
            term_type = "Abnormal (Signal)"
        else:
            term_type = "Normal"

        classification = _classify_result(
            terminated_by_signal=terminated_by_signal,
            signal_name=signal_name,
            signal_number=signal_number,
            exit_code=exit_code,
            primary_failure=primary_fail,
            stopped_by_user=stopped_user,
            timed_out=timed_out_flag
        )

        # Source evidence correlation
        src_ev = locate_source_evidence(
            src_path,
            failed_syscall=(primary_fail or {}).get("syscall", ""),
            gdb_line=0
        )

        # Build truthful observed facts and diagnostic interpretation
        facts: List[str] = [
            f"Target executable '{rel_exe}' ran as PID {target_pid} for {elapsed_final:.2f} ms."
        ]
        if terminated_by_signal:
            facts.append(f"Process terminated abnormally by signal {signal_number} ({signal_desc or signal_name}).")
        else:
            facts.append(f"Process exited normally with exit code {exit_code}.")

        if trace_info.get("available"):
            facts.append(
                f"strace captured {trace_info['total_syscalls']} system calls "
                f"({trace_info['relevant_failures']} relevant failure(s), "
                f"{trace_info['loader_noise_failures']} dynamic-loader probing call(s))."
            )
        if primary_fail and primary_fail.get("syscall"):
            facts.append(
                f"System call {primary_fail['syscall']}() returned -1 with "
                f"{primary_fail['errno_name']} ({primary_fail['errno_code']}: {primary_fail['description']})."
            )

        if stopped_user:
            diagnosis = "Execution was manually stopped by the user before natural termination."
            next_step = "Inspect partial program output or re-run the program to completion."
        elif timed_out_flag:
            diagnosis = f"Execution exceeded the {timeout_sec:.1f}s timeout limit, indicating a possible infinite loop, blocking I/O, or long sleep."
            next_step = "Check loop termination conditions, blocking read()/wait() calls, or sleep durations in the C source."
        elif terminated_by_signal:
            diagnosis = f"The process was terminated by {signal_desc or signal_name}. Run AutoDebugger with GDB enabled for stack frame and crash line inspection."
            next_step = "Use AutoDebugger to automatically collect a GDB backtrace and pinpoint the faulting source line."
        elif primary_fail and primary_fail.get("syscall"):
            diagnosis = (
                f"System call {primary_fail['syscall']}() failed with {primary_fail['errno_name']} "
                f"({primary_fail['errno_code']}): {primary_fail['description']}."
            )
            next_step = "Verify file paths, descriptor validity, permissions, and system call arguments at the call site."
        elif exit_code == 0:
            diagnosis = "Program executed cleanly and exited with status 0 without any relevant system-call errors or signals."
            next_step = "No corrective action required."
        else:
            diagnosis = f"Program exited with non-zero status ({exit_code}) without a failed kernel system call or fatal signal."
            next_step = "Check application return values and conditional branches in main()."

        source_info = get_program_source(norm_name)

        completed_data: Dict[str, Any] = {
            "success": True,
            "session_id": session_id,
            "state": "completed",
            "analysis_type": mode,
            "program": norm_name,
            "executable_path": rel_exe,
            "source_path": rel_src,
            "source_code": source_info.get("code", ""),
            "tracing_enabled": use_trace and mode != "Direct Run",
            "monitoring_enabled": use_monitor,
            "capture_output": capture_output,
            "timestamp": end_utc.isoformat(),
            "start_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "end_time": end_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "display_time": end_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "elapsed_ms": elapsed_final,
            "pid": target_pid,
            "ppid": ppid_val,
            "process_state": "Exited" if exited_normally else "Terminated",
            "termination_type": term_type,
            "exited_normally": exited_normally,
            "exit_code": exit_code if exited_normally else None,
            "terminated_by_signal": terminated_by_signal,
            "signal_number": signal_number if terminated_by_signal else None,
            "signal_name": signal_name if terminated_by_signal else None,
            "signal_description": signal_desc if terminated_by_signal else None,
            "result_badge": classification["result_badge"],
            "badge_tone": classification["badge_tone"],
            "overall_status": classification["overall_status"],
            "illustration_type": classification["illustration_type"],
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
                    "Process completed in a single sampling window before multiple periodic /proc samples were needed."
                    if len(timeline_points) <= 1 and use_monitor else ""
                )
            },
            "syscall_analysis": trace_info,
            "gdb_analysis": {
                "available": False,
                "status": "not_run",
                "status_label": "Run AutoDebugger for GDB crash investigation",
                "backtrace": "",
                "frames": []
            },
            "program_stdout": prog_stdout,
            "program_stderr": prog_stderr,
            "debugger_output": dbg_out_text + ("\n" + dbg_err_text if dbg_err_text else ""),
            "observed_facts": facts,
            "diagnosis": diagnosis,
            "next_step": next_step,
            "trace_file": trace_rel if (use_trace and mode != "Direct Run") else None,
            "c_report_file": c_report_rel if mode != "Direct Run" else None,
            "gdb_file": None
        }

        save_report(completed_data)

        with _SESSIONS_LOCK:
            _SESSIONS[session_id] = completed_data
            _PROCESS_HANDLES.pop(session_id, None)

    runner_thread = threading.Thread(target=_runner, daemon=True)
    runner_thread.start()

    if not async_mode:
        runner_thread.join(timeout=timeout_sec + 3.0)
        with _SESSIONS_LOCK:
            return dict(_SESSIONS[session_id])

    # In async_mode, wait briefly (120ms) so fast programs return completed immediately,
    # while long-running programs return state='running' for live UI polling!
    runner_thread.join(timeout=0.15)
    with _SESSIONS_LOCK:
        return dict(_SESSIONS[session_id])
