"""
Real strace System-Call and errno Analysis Service for LDST.
Parses actual strace trace logs, classifies application failures vs loader/probing noise,
groups failed system calls, and correlates failures with C source lines where determinable.
"""

import os
import re
from typing import Dict, Any, List, Optional

ERRNO_CATALOG: Dict[str, Dict[str, Any]] = {
    "EPERM":        {"code": 1,   "description": "Operation not permitted"},
    "ENOENT":       {"code": 2,   "description": "No such file or directory"},
    "ESRCH":        {"code": 3,   "description": "No such process"},
    "EINTR":        {"code": 4,   "description": "Interrupted system call"},
    "EIO":          {"code": 5,   "description": "Input/output error"},
    "ENXIO":        {"code": 6,   "description": "No such device or address"},
    "E2BIG":        {"code": 7,   "description": "Argument list too long"},
    "ENOEXEC":      {"code": 8,   "description": "Exec format error"},
    "EBADF":        {"code": 9,   "description": "Bad file descriptor"},
    "ECHILD":       {"code": 10,  "description": "No child processes"},
    "EAGAIN":       {"code": 11,  "description": "Resource temporarily unavailable"},
    "EWOULDBLOCK":  {"code": 11,  "description": "Resource temporarily unavailable"},
    "ENOMEM":       {"code": 12,  "description": "Cannot allocate memory"},
    "EACCES":       {"code": 13,  "description": "Permission denied"},
    "EFAULT":       {"code": 14,  "description": "Bad address"},
    "EBUSY":        {"code": 16,  "description": "Device or resource busy"},
    "EEXIST":       {"code": 17,  "description": "File exists"},
    "EXDEV":        {"code": 18,  "description": "Invalid cross-device link"},
    "ENODEV":       {"code": 19,  "description": "No such device"},
    "ENOTDIR":      {"code": 20,  "description": "Not a directory"},
    "EISDIR":       {"code": 21,  "description": "Is a directory"},
    "EINVAL":       {"code": 22,  "description": "Invalid argument"},
    "ENFILE":       {"code": 23,  "description": "Too many open files in system"},
    "EMFILE":       {"code": 24,  "description": "Too many open files"},
    "ENOTTY":       {"code": 25,  "description": "Inappropriate ioctl for device"},
    "ETXTBSY":      {"code": 26,  "description": "Text file busy"},
    "EFBIG":        {"code": 27,  "description": "File too large"},
    "ENOSPC":       {"code": 28,  "description": "No space left on device"},
    "ESPIPE":       {"code": 29,  "description": "Illegal seek"},
    "EROFS":        {"code": 30,  "description": "Read-only file system"},
    "EMLINK":       {"code": 31,  "description": "Too many links"},
    "EPIPE":        {"code": 32,  "description": "Broken pipe"},
    "EDOM":         {"code": 33,  "description": "Numerical argument out of domain"},
    "ERANGE":       {"code": 34,  "description": "Numerical result out of range"},
    "EDEADLK":      {"code": 35,  "description": "Resource deadlock avoided"},
    "ENAMETOOLONG": {"code": 36,  "description": "File name too long"},
    "ENOSYS":       {"code": 38,  "description": "Function not implemented"},
    "ENOTEMPTY":    {"code": 39,  "description": "Directory not empty"},
    "ELOOP":        {"code": 40,  "description": "Too many levels of symbolic links"},
    "EADDRINUSE":   {"code": 98,  "description": "Address already in use"},
    "ECONNRESET":   {"code": 104, "description": "Connection reset by peer"},
    "ETIMEDOUT":    {"code": 110, "description": "Connection timed out"},
    "ECONNREFUSED": {"code": 111, "description": "Connection refused"}
}

SYSCALL_LINE_RE = re.compile(
    r"^\s*(?:(\d+)\s+)?([a-zA-Z0-9_]+)\((.*)\)\s*=\s*(-?\d+|\?|0x[0-9a-fA-F]+)(?:\s+([A-Z0-9_]+)\s*(?:\(([^)]+)\))?)?.*$"
)
SIGNAL_LINE_RE = re.compile(r"^\s*(?:(\d+)\s+)?(?:---\s+(SIG[A-Z0-9]+)\s+\{(.*)\}\s+---|\+\+\+\s+killed by\s+(SIG[A-Z0-9]+).*\+\+\+)")


def is_loader_noise_call(syscall: str, errno_name: str, args_str: str) -> bool:
    """
    Conservatively identify standard glibc / dynamic-loader probing calls
    or test-file cleanup unlink() calls that return ENOENT.
    """
    if syscall == "access" and errno_name == "ENOENT" and "/etc/ld.so.preload" in args_str:
        return True
    if errno_name == "ENOENT" and (
        "/etc/ld.so." in args_str or
        "glibc-hwcaps" in args_str or
        "/tls/" in args_str
    ):
        return True
    if syscall == "unlink" and errno_name == "ENOENT":
        return True
    return False


def parse_trace_file(trace_path: str) -> Dict[str, Any]:
    """
    Parse a real strace log file into structured syscall counts, grouped failures,
    signal events, and raw trace text.
    """
    if not trace_path or not os.path.isfile(trace_path):
        return {
            "available": False,
            "trace_path": trace_path or "",
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

    with open(trace_path, "r", encoding="utf-8", errors="replace") as f:
        raw_content = f.read()

    lines = raw_content.splitlines()
    total_syscalls = 0
    total_failures = 0
    relevant_failures = 0
    loader_noise_failures = 0

    syscall_freq: Dict[str, int] = {}
    grouped_map: Dict[str, Dict[str, Any]] = {}
    all_failures_list: List[Dict[str, Any]] = []
    signals_list: List[Dict[str, Any]] = []
    primary_failure: Optional[Dict[str, Any]] = None

    for idx, line in enumerate(lines, start=1):
        sig_m = SIGNAL_LINE_RE.match(line)
        if sig_m:
            pid_s, sig1, sig_details, sig2 = sig_m.groups()
            sig_name = sig1 or sig2
            signals_list.append({
                "line_number": idx,
                "pid": int(pid_s) if pid_s else None,
                "signal": sig_name,
                "details": sig_details or "Process terminated by signal",
                "raw": line.strip()
            })
            continue

        m = SYSCALL_LINE_RE.match(line)
        if not m:
            continue

        pid_s, syscall, args_str, ret_val, errno_name, errno_desc_inline = m.groups()
        total_syscalls += 1
        syscall_freq[syscall] = syscall_freq.get(syscall, 0) + 1

        if ret_val == "-1" and errno_name:
            total_failures += 1
            cat_entry = ERRNO_CATALOG.get(errno_name, {})
            errno_code = cat_entry.get("code", -1)
            description = errno_desc_inline or cat_entry.get("description", "Linux reported an error for this system call")
            noise = is_loader_noise_call(syscall, errno_name, args_str)

            if noise:
                loader_noise_failures += 1
            else:
                relevant_failures += 1

            failure_item = {
                "line_number": idx,
                "pid": int(pid_s) if pid_s else None,
                "syscall": syscall,
                "args": args_str,
                "return_value": -1,
                "errno_name": errno_name,
                "errno_code": errno_code,
                "description": description,
                "is_noise": noise,
                "classification": "Loader/Setup Probing (Ignored)" if noise else "Application Failure",
                "raw": line.strip()
            }
            all_failures_list.append(failure_item)

            if not noise:
                primary_failure = failure_item

            group_key = f"{syscall}:{errno_name}:{'noise' if noise else 'app'}"
            if group_key not in grouped_map:
                grouped_map[group_key] = {
                    "syscall": f"{syscall}()",
                    "syscall_raw": syscall,
                    "result": "Failed (-1)",
                    "return_value": -1,
                    "errno_name": errno_name,
                    "errno_code": errno_code,
                    "description": description,
                    "count": 0,
                    "is_noise": noise,
                    "classification": "Loader/Environment Noise" if noise else "Target Program Failure",
                    "evidence_lines": []
                }
            grouped_map[group_key]["count"] += 1
            if len(grouped_map[group_key]["evidence_lines"]) < 10:
                grouped_map[group_key]["evidence_lines"].append(line.strip())

    # Sort grouped failures: relevant application failures first, then by count descending
    grouped_failures = sorted(
        grouped_map.values(),
        key=lambda g: (1 if g["is_noise"] else 0, -g["count"])
    )

    syscall_counts = [
        {"syscall": f"{k}()", "count": v}
        for k, v in sorted(syscall_freq.items(), key=lambda item: -item[1])
    ]

    return {
        "available": True,
        "trace_path": trace_path,
        "total_syscalls": total_syscalls,
        "total_failures": total_failures,
        "relevant_failures": relevant_failures,
        "loader_noise_failures": loader_noise_failures,
        "grouped_failures": grouped_failures,
        "all_failures": all_failures_list,
        "syscall_counts": syscall_counts[:25],
        "signals": signals_list,
        "primary_failure": primary_failure,
        "raw_trace": raw_content[:262144]
    }


def locate_source_evidence(
    source_path: str,
    failed_syscall: str = "",
    gdb_line: int = 0
) -> Optional[Dict[str, Any]]:
    """
    Locate relevant C source lines when reliably known:
    1. If GDB provided an exact line number (gdb_line > 0), use that exact line.
    2. Otherwise, if a failed syscall was recorded (e.g. openat -> open/fopen, read -> read),
       search the C source file for the corresponding C library/system call invocation.
    Never invents a line number if no match is found.
    """
    if not source_path or not os.path.isfile(source_path):
        return None

    try:
        with open(source_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except Exception:
        return None

    if not lines:
        return None

    target_line = 0
    attribution_method = ""

    if gdb_line and 1 <= gdb_line <= len(lines):
        target_line = gdb_line
        attribution_method = "GDB stack frame (#0)"
    elif failed_syscall:
        sc = failed_syscall.replace("()", "").strip()
        # Map kernel syscall names to C user-space call names
        candidates = [sc]
        if sc in ("openat", "open"):
            candidates = ["open", "fopen", "opendir"]
        elif sc in ("newfstatat", "fstat", "statx"):
            candidates = ["stat", "fstat", "lstat"]
        elif sc in ("tgkill", "kill", "tkill"):
            candidates = ["raise", "kill", "abort"]

        matched_lines = []
        for idx, text in enumerate(lines, start=1):
            stripped = text.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            for cand in candidates:
                if re.search(rf"\b{re.escape(cand)}\s*\(", text):
                    matched_lines.append(idx)
                    break

        if matched_lines:
            # Take the last matching call in the source (or only match)
            target_line = matched_lines[-1]
            attribution_method = f"Source call match for {sc}()"

    if target_line <= 0:
        return None

    start_l = max(1, target_line - 3)
    end_l = min(len(lines), target_line + 3)
    snippet = []
    for lno in range(start_l, end_l + 1):
        snippet.append({
            "line": lno,
            "code": lines[lno - 1],
            "is_target": lno == target_line
        })

    return {
        "file": os.path.basename(source_path),
        "source_path": source_path,
        "line": target_line,
        "code_line": lines[target_line - 1].strip(),
        "attribution": attribution_method,
        "snippet": snippet
    }
