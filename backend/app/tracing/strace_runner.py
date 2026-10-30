"""
Linux System Debugging Tool - System Call Tracing & strace Parser
Parses strace outputs, identifies failed syscalls, and explains POSIX errnos clearly.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import toolchain

SYSCALL_PATTERN = re.compile(
    r"^(?P<syscall>[a-zA-Z0-9_]+)\((?P<args>.*)\)\s+=\s+(?P<result>-?\d+|0x[0-9a-fA-F]+|\?)(?:\s+(?P<errno_name>[A-Z0-9]+)\s+\((?P<errno_desc>[^)]+)\))?.*$"
)

ERRNO_EXPLANATIONS = {
    "ENOENT": "No such file or directory. The application attempted to access a path that does not exist.",
    "EACCES": "Permission denied. The process lacked required read/write/execute permissions.",
    "EBADF": "Bad file descriptor. An I/O operation was attempted on an invalid, uninitialized, or already closed file descriptor.",
    "EINVAL": "Invalid argument. One or more parameters passed to the system call were invalid.",
    "ENOMEM": "Out of memory. Memory allocation failed or process exceeded memory resource limits.",
    "EPIPE": "Broken pipe. Attempted write to a pipe or socket with no active reading process.",
    "EMFILE": "Too many open files. The process reached its maximum file descriptor limit.",
    "EADDRINUSE": "Address already in use. Attempted to bind to a port or socket that is already occupied.",
    "ECONNREFUSED": "Connection refused. Target host rejected the connection request.",
    "ETIMEDOUT": "Connection timed out. Network or I/O operation did not complete within the timeout limit."
}


def parse_strace_output(raw_trace: str) -> List[Dict[str, Any]]:
    """Parses strace output into structured system call events."""
    events: List[Dict[str, Any]] = []

    for line in raw_trace.splitlines():
        line = line.strip()
        if not line or line.startswith("+++") or line.startswith("---"):
            continue

        m = SYSCALL_PATTERN.match(line)
        if m:
            syscall = m.group("syscall")
            args = m.group("args")
            result = m.group("result")
            errno_name = m.group("errno_name")
            errno_desc = m.group("errno_desc")

            is_error = bool(errno_name or (result and result.startswith("-")))
            explanation = ERRNO_EXPLANATIONS.get(errno_name, errno_desc or "") if errno_name else ""

            events.append({
                "syscall": syscall,
                "args": args,
                "result": result,
                "is_error": is_error,
                "errno": errno_name,
                "errno_description": explanation,
                "raw": line
            })
        else:
            events.append({
                "syscall": "other",
                "args": "",
                "result": "",
                "is_error": False,
                "errno": None,
                "errno_description": "",
                "raw": line
            })

    return events


def run_strace_on_target(executable_path: str, args: Optional[List[str]] = None,
                         working_dir: Optional[str] = None, timeout: float = 15.0) -> Dict[str, Any]:
    """Runs target program under strace and returns parsed system call events."""
    cmd = ["strace", "-f", "-s", "128", executable_path]
    if args:
        cmd.extend(args)

    ret, stdout, stderr = toolchain.run_tool_cmd(cmd, cwd=working_dir, timeout=timeout)
    # strace logs to stderr by default
    trace_events = parse_strace_output(stderr)
    failed_calls = [e for e in trace_events if e["is_error"]]

    return {
        "returncode": ret,
        "stdout": stdout,
        "total_syscalls": len(trace_events),
        "failed_syscalls_count": len(failed_calls),
        "events": trace_events,
        "failed_events": failed_calls
    }
