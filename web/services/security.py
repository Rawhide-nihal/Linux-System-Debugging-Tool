"""
Security, Path Validation, and Environment Inspection for LDST.
Ensures safe local execution, prevents directory traversal and shell command injection,
and inspects real Linux toolchain availability.
"""

import os
import re
import shutil
import subprocess
from typing import Dict, Any, Tuple

# Project root directory (Linux-System-Debugging-Tool/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TESTS_DIR = os.path.join(PROJECT_ROOT, "tests")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
TRACES_DIR = os.path.join(PROJECT_ROOT, "traces")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

# Official built-in test programs
OFFICIAL_PROGRAMS = {
    "normal_test": {
        "name": "normal_test",
        "title": "Normal Execution",
        "category": "Clean Execution",
        "badge": "EXIT 0",
        "description": "A simple C program that executes standard output operations and terminates normally with exit status 0.",
        "expected_outcome": "Normal exit (0), no failed system calls, no fatal signals."
    },
    "file_error": {
        "name": "file_error",
        "title": "File Error (ENOENT)",
        "category": "File System Error",
        "badge": "ENOENT",
        "description": "Demonstrates a failed open() system call on a nonexistent file ('missing_file.txt'), setting errno to ENOENT (2).",
        "expected_outcome": "openat() returns -1 with ENOENT (2: No such file or directory); exits with status 1."
    },
    "invalid_fd": {
        "name": "invalid_fd",
        "title": "Invalid File Descriptor (EBADF)",
        "category": "Descriptor Error",
        "badge": "EBADF",
        "description": "Attempts a read() system call using an invalid file descriptor (-1), setting errno to EBADF (9).",
        "expected_outcome": "read() returns -1 with EBADF (9: Bad file descriptor); exits with status 1."
    },
    "permission_error": {
        "name": "permission_error",
        "title": "Permission Error (EACCES)",
        "category": "Access Control Error",
        "badge": "EACCES",
        "description": "Creates a temporary target file, restricts mode to 0000 via chmod(), and attempts open() for reading.",
        "expected_outcome": "openat() returns -1 with EACCES (13: Permission denied); exits with status 1."
    },
    "system_call_error": {
        "name": "system_call_error",
        "title": "System Call Error",
        "category": "System Call Failure",
        "badge": "EBADF",
        "description": "Demonstrates a controlled system-call failure by invoking read(999, ...) on an unopened descriptor and handling the error.",
        "expected_outcome": "read(999, ...) returns -1 with EBADF (9: Bad file descriptor); program handles failure and exits with 0."
    },
    "abnormal_exit": {
        "name": "abnormal_exit",
        "title": "Abnormal Termination (SIGTERM)",
        "category": "Signal Termination",
        "badge": "SIGTERM",
        "description": "Demonstrates abnormal process termination by sending SIGTERM (15) to itself via raise(SIGTERM).",
        "expected_outcome": "Abnormal termination by signal 15 (SIGTERM)."
    },
    "segmentation_fault": {
        "name": "segmentation_fault",
        "title": "Segmentation Fault (SIGSEGV)",
        "category": "Memory Crash",
        "badge": "SIGSEGV",
        "description": "Triggers a controlled segmentation fault by dereferencing a NULL pointer (*ptr = 42), invoking SIGSEGV and GDB crash analysis.",
        "expected_outcome": "Abnormal crash by signal 11 (SIGSEGV) at segmentation_fault.c:9."
    },
    "math_step": {
        "name": "math_step",
        "title": "Local Variables & Stepping",
        "category": "Source Stepping",
        "badge": "STEPPING",
        "description": "Demonstrates local variable assignments (a, b, c) and arithmetic computation with real-time value inspection at each source line.",
        "expected_outcome": "Line-by-line stepping shows variables a=10, b=20, c=30; outputs calculated sum; exits 0."
    },
    "function_call": {
        "name": "function_call",
        "title": "Function Call (Step In / Out)",
        "category": "Stack & Functions",
        "badge": "CALL STACK",
        "description": "Demonstrates function call frame transitions. User can Step Into add(), inspect argument frames (x, y), and Step Out to main().",
        "expected_outcome": "Call stack frames #0 add() and #1 main(); arguments inspected; return to caller; exits 0."
    },
    "sigfpe_test": {
        "name": "sigfpe_test",
        "title": "Arithmetic Error (SIGFPE)",
        "category": "Arithmetic Crash",
        "badge": "SIGFPE",
        "description": "Triggers an intentional division by zero (42 / 0) to demonstrate hardware arithmetic trap detection and SIGFPE attribution.",
        "expected_outcome": "Abnormal crash by signal 8 (SIGFPE) at line 8 with stack frame and statement attribution."
    },
    "nonzero_exit": {
        "name": "nonzero_exit",
        "title": "Deliberate Non-Zero Exit",
        "category": "Status Code Test",
        "badge": "EXIT 42",
        "description": "Demonstrates a program returning a deliberate non-zero exit code (42) without any signal or crash.",
        "expected_outcome": "Clean execution terminating with exit status 42 (clearly distinguished as not a crash)."
    }
}

VALID_PROGRAM_NAME_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$")

RESERVED_NAMES = {
    "debugger", "autodebug", "ldst", "makefile", "setup", "run", "selftest",
    "con", "prn", "aux", "nul"
}


def ensure_directories() -> None:
    """Ensure all required runtime directories exist."""
    for d in (TESTS_DIR, LOGS_DIR, TRACES_DIR, REPORTS_DIR, RESULTS_DIR):
        os.makedirs(d, exist_ok=True)


def validate_program_name(raw_name: str, allow_official: bool = True) -> Tuple[bool, str, str]:
    """
    Validate a program name strictly.
    Returns (is_valid, normalized_name, error_message).
    """
    if not raw_name or not isinstance(raw_name, str):
        return False, "", "Program name is required."

    cleaned = raw_name.strip()
    if cleaned.startswith("tests/"):
        cleaned = cleaned[len("tests/"):]
    elif cleaned.startswith("./tests/"):
        cleaned = cleaned[len("./tests/"):]

    if cleaned.endswith(".c"):
        cleaned = cleaned[:-2]

    # Reject any path traversal or directory separators or shell metacharacters
    if "/" in cleaned or "\\" in cleaned or ".." in cleaned or "\x00" in cleaned:
        return False, "", "Invalid program name: path separators and directory traversal ('..') are forbidden."

    if not VALID_PROGRAM_NAME_RE.match(cleaned):
        return False, "", (
            "Invalid program name. Use 1-64 characters: letters, digits, underscores (_), or hyphens (-), "
            "starting with a letter, digit, or underscore."
        )

    if cleaned.lower() in RESERVED_NAMES:
        return False, "", f"'{cleaned}' is a reserved system name."

    if not allow_official and cleaned in OFFICIAL_PROGRAMS:
        return False, "", f"'{cleaned}' is an official built-in test program and cannot be overwritten or deleted."

    # Verify resolved paths remain strictly inside TESTS_DIR
    src_path = os.path.realpath(os.path.join(TESTS_DIR, f"{cleaned}.c"))
    exe_path = os.path.realpath(os.path.join(TESTS_DIR, cleaned))
    tests_real = os.path.realpath(TESTS_DIR)

    if not src_path.startswith(tests_real + os.sep) or not exe_path.startswith(tests_real + os.sep):
        return False, "", "Security error: resolved path escapes the approved tests/ directory."

    return True, cleaned, ""


def get_program_paths(program_name: str) -> Tuple[str, str, str]:
    """
    Return (normalized_name, abs_source_path, abs_executable_path) for a validated program.
    Raises ValueError if invalid.
    """
    ok, norm, err = validate_program_name(program_name, allow_official=True)
    if not ok:
        raise ValueError(err)
    src_path = os.path.join(TESTS_DIR, f"{norm}.c")
    exe_path = os.path.join(TESTS_DIR, norm)
    return norm, src_path, exe_path


def _tool_version(cmd: list) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        out = (res.stdout or res.stderr or "").strip()
        return out.splitlines()[0] if out else "Available"
    except Exception:
        return "Available"


def check_environment() -> Dict[str, Any]:
    """
    Inspect the real Linux environment and required debugging tools.
    Never fabricates availability.
    """
    ensure_directories()

    gcc_path = shutil.which("gcc")
    make_path = shutil.which("make")
    strace_path = shutil.which("strace")
    gdb_path = shutil.which("gdb")

    debugger_bin = os.path.join(PROJECT_ROOT, "debugger")
    autodebug_bin = os.path.join(PROJECT_ROOT, "autodebug")
    ldst_bin = os.path.join(PROJECT_ROOT, "ldst")

    proc_available = os.path.isdir("/proc") and os.path.isfile("/proc/stat")

    uname_info = "Linux"
    try:
        res = subprocess.run(["uname", "-sr"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            uname_info = res.stdout.strip()
    except Exception:
        pass

    return {
        "os": uname_info,
        "procfs_available": proc_available,
        "tools": {
            "gcc": {
                "available": bool(gcc_path),
                "path": gcc_path or "Not found",
                "version": _tool_version(["gcc", "--version"]) if gcc_path else "Unavailable",
                "install_hint": "sudo apt install build-essential"
            },
            "make": {
                "available": bool(make_path),
                "path": make_path or "Not found",
                "version": _tool_version(["make", "--version"]) if make_path else "Unavailable",
                "install_hint": "sudo apt install build-essential"
            },
            "strace": {
                "available": bool(strace_path),
                "path": strace_path or "Not found",
                "version": _tool_version(["strace", "--version"]) if strace_path else "Unavailable",
                "install_hint": "sudo apt install strace"
            },
            "gdb": {
                "available": bool(gdb_path),
                "path": gdb_path or "Not found",
                "version": _tool_version(["gdb", "--version"]) if gdb_path else "Unavailable",
                "install_hint": "sudo apt install gdb"
            }
        },
        "core_binaries": {
            "debugger": {
                "available": os.path.isfile(debugger_bin) and os.access(debugger_bin, os.X_OK),
                "path": "debugger"
            },
            "autodebug": {
                "available": os.path.isfile(autodebug_bin) and os.access(autodebug_bin, os.X_OK),
                "path": "autodebug"
            },
            "ldst": {
                "available": os.path.isfile(ldst_bin) and os.access(ldst_bin, os.X_OK),
                "path": "ldst"
            }
        }
    }
