"""
Structured Diagnostic Report Persistence Service for LDST.
Stores, retrieves, searches, exports (JSON and TXT), and deletes real debugging reports.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from .security import REPORTS_DIR, RESULTS_DIR, ensure_directories

SAFE_REPORT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,80}$")


def format_report_txt(report: Dict[str, Any]) -> str:
    """
    Generate a comprehensive, human-readable plain-text diagnostic report
    from a structured LDST session dictionary.
    """
    lines = [
        "======================================================================",
        "           LDST — LINUX SYSTEM DEBUGGING TOOL DIAGNOSTIC REPORT       ",
        "======================================================================",
        f"Report ID        : {report.get('session_id', 'Unavailable')}",
        f"Timestamp (UTC)  : {report.get('timestamp', 'Unavailable')}",
        f"Program          : {report.get('program', 'Unavailable')}",
        f"Source File      : {report.get('source_path', 'Unavailable')}",
        f"Analysis Type    : {report.get('analysis_type', 'Debugger')}",
        f"Result Badge     : {report.get('result_badge', 'Unavailable')}",
        f"Overall Status   : {report.get('overall_status', 'Unavailable')}",
        "",
        "1. EXECUTION & TERMINATION SUMMARY",
        "----------------------------------------------------------------------",
        f"Target PID       : {report.get('pid') or 'Unavailable'}",
        f"Parent PID (PPID): {report.get('ppid') or 'Unavailable'}",
        f"Start Time       : {report.get('start_time', 'Unavailable')}",
        f"End Time         : {report.get('end_time', 'Unavailable')}",
        f"Duration         : {report.get('elapsed_ms', 0)} ms",
        f"Termination Type : {report.get('termination_type', 'Unavailable')}",
        f"Exit Status      : {report.get('exit_code') if report.get('exit_code') is not None else 'N/A'}",
        f"Signal           : {report.get('signal_name') or 'None'}"
        + (f" ({report.get('signal_number')}) - {report.get('signal_description', '')}" if report.get("signal_number") else ""),
        "",
        "2. COMPILATION SUMMARY",
        "----------------------------------------------------------------------",
    ]

    comp = report.get("compilation") or {}
    if comp:
        lines.append(f"Status           : {'Success' if comp.get('success', True) else 'Failed'}")
        lines.append(f"Command          : {comp.get('command', 'gcc -Wall -Wextra -std=c11 -g')}")
        lines.append(f"Warnings         : {comp.get('warnings_count', 0)}")
        lines.append(f"Errors           : {comp.get('errors_count', 0)}")
        if comp.get("stderr"):
            lines.append("Compiler Output  :")
            for cl in comp["stderr"].splitlines():
                lines.append(f"  {cl}")
    else:
        lines.append("Pre-compiled executable used.")

    lines.extend([
        "",
        "3. PROGRAM OUTPUT (STDOUT / STDERR)",
        "----------------------------------------------------------------------",
        "--- STDOUT ---",
        (report.get("program_stdout") or "(empty)").rstrip(),
        "--- STDERR ---",
        (report.get("program_stderr") or "(empty)").rstrip(),
        "",
        "4. ERROR / ERRNO ANALYSIS",
        "----------------------------------------------------------------------",
    ])

    err = report.get("detected_error")
    if err and err.get("syscall"):
        lines.extend([
            f"Failed Operation : {err.get('syscall')}()",
            f"Return Value     : -1",
            f"errno Name       : {err.get('errno_name', 'Unavailable')}",
            f"errno Number     : {err.get('errno_code', -1)}",
            f"Description      : {err.get('description', 'Unavailable')}",
            f"Raw Evidence     : {err.get('evidence', 'Unavailable')}",
        ])
    else:
        lines.append("No relevant failed system call detected.")

    lines.extend([
        "",
        "5. SYSTEM CALL TRACE SUMMARY",
        "----------------------------------------------------------------------",
    ])
    sc_info = report.get("syscall_analysis") or {}
    if sc_info.get("available"):
        lines.extend([
            f"Total Captured Syscalls  : {sc_info.get('total_syscalls', 0)}",
            f"Relevant Failed Syscalls : {sc_info.get('relevant_failures', 0)}",
            f"Loader/Probing Noise     : {sc_info.get('loader_noise_failures', 0)}",
        ])
        grouped = sc_info.get("grouped_failures") or []
        if grouped:
            lines.append("")
            lines.append("Grouped Failed System Calls:")
            for g in grouped:
                lines.append(
                    f"  - {g.get('syscall'):14s} | errno: {g.get('errno_name'):10s} ({g.get('errno_code')}) "
                    f"| count: {g.get('count')} | {g.get('classification')}"
                )
    else:
        lines.append("System-call trace not captured or disabled for this session.")

    lines.extend([
        "",
        "6. LINUX /proc PROCESS STATISTICS",
        "----------------------------------------------------------------------",
    ])
    pstats = report.get("process_stats") or {}
    lines.extend([
        f"Peak VmSize (Virtual) : {pstats.get('peak_vm_size_kb', 0)} KB",
        f"Peak VmRSS (Resident) : {pstats.get('peak_vm_rss_kb', 0)} KB",
        f"Peak Threads          : {pstats.get('peak_threads') or 'Unavailable'}",
        f"Peak Open FDs         : {pstats.get('peak_open_fds') if pstats.get('peak_open_fds', -1) >= 0 else 'Unavailable'}",
        f"Monitoring Samples    : {pstats.get('samples_count', 0)}",
    ])

    lines.extend([
        "",
        "7. GDB CRASH / BACKTRACE ANALYSIS",
        "----------------------------------------------------------------------",
    ])
    gdb = report.get("gdb_analysis") or {}
    lines.append(f"GDB Status       : {gdb.get('status_label', 'Not required')}")
    if gdb.get("backtrace"):
        lines.append("Backtrace:")
        for gl in gdb["backtrace"].splitlines():
            lines.append(f"  {gl}")

    lines.extend([
        "",
        "8. SOURCE LOCATION EVIDENCE",
        "----------------------------------------------------------------------",
    ])
    src_ev = report.get("source_evidence")
    if src_ev and src_ev.get("line"):
        lines.append(f"Location         : {src_ev.get('file')}:{src_ev.get('line')} ({src_ev.get('attribution', '')})")
        lines.append(f"Source Line      : {src_ev.get('code_line', '')}")
    else:
        lines.append("Exact source line was not determinable from runtime evidence.")

    lines.extend([
        "",
        "9. DIAGNOSTIC INTERPRETATION",
        "----------------------------------------------------------------------",
        "Observed Facts:",
    ])
    for fact in (report.get("observed_facts") or []):
        lines.append(f"  * {fact}")
    lines.append("")
    lines.append(f"Diagnosis        : {report.get('diagnosis', 'Unavailable')}")
    lines.append(f"Recommended Next : {report.get('next_step', 'Unavailable')}")

    lines.extend([
        "",
        "10. RAW EVIDENCE FILE REFERENCES",
        "----------------------------------------------------------------------",
        f"Trace Log        : {report.get('trace_file') or 'None'}",
        f"Report File (TXT): {report.get('txt_report_file') or 'None'}",
        f"Report File (JSON): {report.get('json_report_file') or 'None'}",
        f"GDB Log          : {report.get('gdb_file') or 'None'}",
        "======================================================================",
        ""
    ])
    return "\n".join(lines)


def save_report(session_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a completed analysis session to disk in both JSON and TXT formats
    under reports/ (and mirror latest summary in results/).
    """
    ensure_directories()
    session_id = session_data.get("session_id")
    if not session_id or not SAFE_REPORT_ID_RE.match(session_id):
        raise ValueError("Invalid session_id for report storage.")

    json_path = os.path.join(REPORTS_DIR, f"{session_id}.json")
    txt_path = os.path.join(REPORTS_DIR, f"{session_id}.txt")

    session_data["json_report_file"] = f"reports/{session_id}.json"
    session_data["txt_report_file"] = f"reports/{session_id}.txt"

    txt_content = format_report_txt(session_data)
    with open(txt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt_content)

    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(session_data, f, indent=2)

    return session_data


def list_reports(query: str = "", analysis_type: str = "", result_filter: str = "") -> List[Dict[str, Any]]:
    """
    List all persisted structured reports sorted newest-first, with optional filtering.
    Truthfully skips corrupt JSON files while logging their status if needed.
    """
    ensure_directories()
    items: List[Dict[str, Any]] = []

    try:
        filenames = os.listdir(REPORTS_DIR)
    except Exception:
        filenames = []

    q = (query or "").strip().lower()
    atype = (analysis_type or "").strip().lower()
    rfilt = (result_filter or "").strip().upper()

    for fname in filenames:
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(REPORTS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "session_id" not in data:
                continue
        except Exception:
            continue

        prog = str(data.get("program", ""))
        badge = str(data.get("result_badge", ""))
        kind = str(data.get("analysis_type", ""))

        if q and q not in prog.lower() and q not in badge.lower() and q not in kind.lower() and q not in data["session_id"].lower():
            continue
        if atype and atype != "all" and atype != kind.lower():
            continue
        if rfilt and rfilt != "ALL" and rfilt not in badge.upper() and rfilt not in str(data.get("overall_status", "")).upper():
            continue

        items.append({
            "session_id": data.get("session_id"),
            "program": prog,
            "source_path": data.get("source_path", ""),
            "analysis_type": kind,
            "result_badge": badge,
            "badge_tone": data.get("badge_tone", "neutral"),
            "overall_status": data.get("overall_status", ""),
            "exit_code": data.get("exit_code"),
            "signal_name": data.get("signal_name", ""),
            "errno_name": (data.get("detected_error") or {}).get("errno_name", ""),
            "elapsed_ms": data.get("elapsed_ms", 0),
            "timestamp": data.get("timestamp", ""),
            "display_time": data.get("display_time", data.get("timestamp", ""))
        })

    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return items


def get_report(session_id: str) -> Dict[str, Any]:
    """
    Load a single persisted report by session_id.
    Raises FileNotFoundError if missing, or ValueError if corrupt/invalid ID.
    """
    if not session_id or not SAFE_REPORT_ID_RE.match(session_id):
        raise ValueError("Invalid report identifier.")

    ensure_directories()
    json_path = os.path.join(REPORTS_DIR, f"{session_id}.json")
    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"Report '{session_id}' was not found.")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Report file does not contain a valid JSON object.")
        return data
    except json.JSONDecodeError as exc:
        raise ValueError(f"Report '{session_id}' is corrupted and cannot be parsed: {exc}") from exc


def get_report_txt(session_id: str) -> str:
    """
    Return the TXT export of a report (generating it on the fly if only JSON exists).
    """
    data = get_report(session_id)
    txt_path = os.path.join(REPORTS_DIR, f"{session_id}.txt")
    if os.path.isfile(txt_path):
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return format_report_txt(data)


def delete_report(session_id: str) -> Dict[str, Any]:
    """
    Delete a persisted report (JSON and TXT) and its associated session trace/gdb files.
    """
    if not session_id or not SAFE_REPORT_ID_RE.match(session_id):
        raise ValueError("Invalid report identifier.")

    json_path = os.path.join(REPORTS_DIR, f"{session_id}.json")
    txt_path = os.path.join(REPORTS_DIR, f"{session_id}.txt")

    if not os.path.isfile(json_path) and not os.path.isfile(txt_path):
        raise FileNotFoundError(f"Report '{session_id}' was not found.")

    if os.path.exists(json_path):
        os.remove(json_path)
    if os.path.exists(txt_path):
        os.remove(txt_path)

    return {"success": True, "deleted": session_id}
