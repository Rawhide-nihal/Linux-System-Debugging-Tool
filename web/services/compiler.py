"""
Real GCC Compilation and Program Management Service for LDST.
Handles discovery of official and custom C programs, safe source editing,
real GCC invocation, diagnostic line parsing, and stale-binary protection.
"""

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

from .security import (
    PROJECT_ROOT,
    TESTS_DIR,
    OFFICIAL_PROGRAMS,
    ensure_directories,
    validate_program_name,
    get_program_paths,
)

COMPILE_STATE_FILE = os.path.join(PROJECT_ROOT, "logs", "compile_state.json")

# Regex for GCC diagnostics: <file>:<line>:<col>: <severity>: <message>
GCC_DIAG_RE = re.compile(r"^([^:\n]+):(\d+):(?:(\d+):)?\s*(fatal error|error|warning|note):\s*(.+)$")


def _load_compile_states() -> Dict[str, Any]:
    if not os.path.isfile(COMPILE_STATE_FILE):
        return {}
    try:
        with open(COMPILE_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_compile_state(name: str, state: Dict[str, Any]) -> None:
    ensure_directories()
    states = _load_compile_states()
    states[name] = state
    try:
        with open(COMPILE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(states, f, indent=2)
    except Exception:
        pass


def parse_gcc_output(stderr_text: str) -> Dict[str, Any]:
    """
    Parse real GCC stderr output into structured diagnostics with line numbers.
    """
    diagnostics: List[Dict[str, Any]] = []
    errors_count = 0
    warnings_count = 0

    for raw_line in (stderr_text or "").splitlines():
        m = GCC_DIAG_RE.match(raw_line.strip())
        if m:
            file_part, line_str, col_str, severity, message = m.groups()
            line_num = int(line_str) if line_str else 0
            col_num = int(col_str) if col_str else 0
            sev_norm = "error" if "error" in severity else severity
            if sev_norm == "error":
                errors_count += 1
            elif sev_norm == "warning":
                warnings_count += 1

            diagnostics.append({
                "file": os.path.basename(file_part),
                "line": line_num,
                "column": col_num,
                "severity": sev_norm,
                "message": message.strip(),
                "raw": raw_line
            })

    return {
        "errors_count": errors_count,
        "warnings_count": warnings_count,
        "diagnostics": diagnostics
    }


def list_programs() -> Dict[str, List[Dict[str, Any]]]:
    """
    Discover all official built-in test programs and user-created custom C programs
    from the tests/ directory.
    """
    ensure_directories()
    compile_states = _load_compile_states()

    builtin_list: List[Dict[str, Any]] = []
    custom_list: List[Dict[str, Any]] = []

    # 1. Built-in official programs in canonical order
    official_order = [
        "normal_test",
        "file_error",
        "invalid_fd",
        "permission_error",
        "system_call_error",
        "abnormal_exit",
        "segmentation_fault"
    ]

    for name in official_order:
        meta = OFFICIAL_PROGRAMS[name]
        src_path = os.path.join(TESTS_DIR, f"{name}.c")
        exe_path = os.path.join(TESTS_DIR, name)
        src_exists = os.path.isfile(src_path)
        exe_exists = os.path.isfile(exe_path) and os.access(exe_path, os.X_OK)

        lines_count = 0
        size_bytes = 0
        modified_iso = None
        if src_exists:
            try:
                st = os.stat(src_path)
                size_bytes = st.st_size
                modified_iso = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
                with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                    lines_count = sum(1 for _ in f)
            except Exception:
                pass

        builtin_list.append({
            "name": name,
            "title": meta["title"],
            "category": meta["category"],
            "badge": meta["badge"],
            "description": meta["description"],
            "expected_outcome": meta["expected_outcome"],
            "is_builtin": True,
            "source_path": f"tests/{name}.c",
            "executable_path": f"tests/{name}",
            "source_exists": src_exists,
            "compiled": exe_exists,
            "compile_status": "compiled" if exe_exists else "not_compiled",
            "lines": lines_count,
            "size_bytes": size_bytes,
            "updated_at": modified_iso
        })

    # 2. Dynamically discover custom .c programs in tests/
    try:
        entries = sorted(os.listdir(TESTS_DIR))
    except Exception:
        entries = []

    for fname in entries:
        if not fname.endswith(".c"):
            continue
        prog_name = fname[:-2]
        if prog_name in OFFICIAL_PROGRAMS:
            continue
        ok, norm_name, _ = validate_program_name(prog_name, allow_official=False)
        if not ok:
            continue

        src_path = os.path.join(TESTS_DIR, f"{norm_name}.c")
        exe_path = os.path.join(TESTS_DIR, norm_name)
        exe_exists = os.path.isfile(exe_path) and os.access(exe_path, os.X_OK)

        lines_count = 0
        size_bytes = 0
        modified_iso = None
        src_mtime = 0.0
        exe_mtime = 0.0
        try:
            st = os.stat(src_path)
            size_bytes = st.st_size
            src_mtime = st.st_mtime
            modified_iso = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                lines_count = sum(1 for _ in f)
        except Exception:
            pass

        if exe_exists:
            try:
                exe_mtime = os.stat(exe_path).st_mtime
            except Exception:
                pass

        cstate = compile_states.get(norm_name, {})
        if cstate.get("status") == "failed":
            compile_status = "failed"
            compiled = False
        elif exe_exists and exe_mtime >= src_mtime - 0.5:
            compile_status = "compiled"
            compiled = True
        else:
            compile_status = "needs_compile"
            compiled = False

        custom_list.append({
            "name": norm_name,
            "title": norm_name.replace("_", " ").replace("-", " ").title(),
            "category": "Custom C Program",
            "badge": "CUSTOM",
            "description": f"User-created C source program ({lines_count} lines).",
            "expected_outcome": "Determined by actual execution and trace analysis.",
            "is_builtin": False,
            "source_path": f"tests/{norm_name}.c",
            "executable_path": f"tests/{norm_name}",
            "source_exists": True,
            "compiled": compiled,
            "compile_status": compile_status,
            "last_compile": cstate,
            "lines": lines_count,
            "size_bytes": size_bytes,
            "updated_at": modified_iso
        })

    return {
        "builtin": builtin_list,
        "custom": custom_list
    }


def get_program_source(program_name: str) -> Dict[str, Any]:
    """
    Read and return the real C source code and metadata of a program.
    """
    norm_name, src_path, exe_path = get_program_paths(program_name)
    if not os.path.isfile(src_path):
        raise FileNotFoundError(f"Source file 'tests/{norm_name}.c' was not found.")

    with open(src_path, "r", encoding="utf-8", errors="replace") as f:
        source_code = f.read()

    exe_exists = os.path.isfile(exe_path) and os.access(exe_path, os.X_OK)
    cstate = _load_compile_states().get(norm_name, {})

    return {
        "name": norm_name,
        "is_builtin": norm_name in OFFICIAL_PROGRAMS,
        "source_path": f"tests/{norm_name}.c",
        "executable_path": f"tests/{norm_name}",
        "compiled": exe_exists and cstate.get("status") != "failed",
        "compile_state": cstate,
        "code": source_code,
        "lines": source_code.splitlines()
    }


def save_custom_program(program_name: str, code: str) -> Dict[str, Any]:
    """
    Save a custom C program inside tests/.
    Validates program name and removes any stale binary until recompiled.
    """
    ok, norm_name, err = validate_program_name(program_name, allow_official=False)
    if not ok:
        raise ValueError(err)

    if code is None or not isinstance(code, str) or not code.strip():
        raise ValueError("Source code cannot be empty. Please provide valid C source code.")

    if len(code.encode("utf-8")) > 512 * 1024:
        raise ValueError("Source file exceeds maximum allowed size (512 KB).")

    ensure_directories()
    src_path = os.path.join(TESTS_DIR, f"{norm_name}.c")
    exe_path = os.path.join(TESTS_DIR, norm_name)

    # Remove stale executable when source is modified so an older binary can never be run accidentally
    if os.path.exists(exe_path):
        try:
            os.remove(exe_path)
        except OSError:
            pass

    with open(src_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)

    _save_compile_state(norm_name, {
        "status": "needs_compile",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return {
        "success": True,
        "name": norm_name,
        "source_path": f"tests/{norm_name}.c",
        "executable_path": f"tests/{norm_name}",
        "bytes_written": len(code.encode("utf-8")),
        "lines": len(code.splitlines())
    }


def compile_program(program_name: str, code: str = None) -> Dict[str, Any]:
    """
    Compile a program using real GCC with -Wall -Wextra -std=c11 -g.
    If code is provided for a custom program, saves it first.
    Removes any prior executable before running GCC so a failed compilation
    never leaves a stale executable behind.
    """
    if code is not None:
        # Save custom program first (raises ValueError on invalid name or empty source)
        save_custom_program(program_name, code)

    norm_name, src_path, exe_path = get_program_paths(program_name)

    if not os.path.isfile(src_path):
        return {
            "success": False,
            "name": norm_name,
            "source_path": f"tests/{norm_name}.c",
            "executable_path": f"tests/{norm_name}",
            "return_code": -1,
            "error": f"Source file 'tests/{norm_name}.c' does not exist.",
            "stdout": "",
            "stderr": f"gcc: error: tests/{norm_name}.c: No such file or directory",
            "errors_count": 1,
            "warnings_count": 0,
            "diagnostics": []
        }

    # Check if source file is empty
    with open(src_path, "r", encoding="utf-8", errors="replace") as f:
        src_content = f.read()
    if not src_content.strip():
        if os.path.exists(exe_path):
            try:
                os.remove(exe_path)
            except OSError:
                pass
        state = {
            "status": "failed",
            "return_code": 1,
            "errors_count": 1,
            "warnings_count": 0,
            "stderr": f"tests/{norm_name}.c:1:1: error: source file is empty (missing main function)",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        _save_compile_state(norm_name, state)
        return {
            "success": False,
            "name": norm_name,
            "source_path": f"tests/{norm_name}.c",
            "executable_path": f"tests/{norm_name}",
            "return_code": 1,
            "stdout": "",
            "stderr": state["stderr"],
            "errors_count": 1,
            "warnings_count": 0,
            "diagnostics": [{
                "file": f"{norm_name}.c",
                "line": 1,
                "column": 1,
                "severity": "error",
                "message": "source file is empty (missing main function)",
                "raw": state["stderr"]
            }]
        }

    gcc_bin = shutil.which("gcc")
    if not gcc_bin:
        return {
            "success": False,
            "name": norm_name,
            "source_path": f"tests/{norm_name}.c",
            "executable_path": f"tests/{norm_name}",
            "return_code": -1,
            "error": "GCC compiler was not found on this system. Install it with: sudo apt install build-essential",
            "stdout": "",
            "stderr": "gcc: command not found (Install with: sudo apt install build-essential)",
            "errors_count": 1,
            "warnings_count": 0,
            "diagnostics": []
        }

    # Remove existing executable BEFORE compiling to prevent stale binary execution on failure
    if os.path.exists(exe_path):
        try:
            os.remove(exe_path)
        except OSError:
            pass

    rel_src = f"tests/{norm_name}.c"
    rel_exe = f"tests/{norm_name}"
    cmd = [gcc_bin, "-Wall", "-Wextra", "-std=c11", "-g", "-O0", rel_src, "-o", rel_exe]

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=20
        )
        duration_ms = round((time.monotonic() - t0) * 1000.0, 2)
    except subprocess.TimeoutExpired:
        state = {
            "status": "failed",
            "return_code": -1,
            "errors_count": 1,
            "warnings_count": 0,
            "stderr": "Compilation timed out after 20 seconds.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        _save_compile_state(norm_name, state)
        return {
            "success": False,
            "name": norm_name,
            "source_path": rel_src,
            "executable_path": rel_exe,
            "return_code": -1,
            "stdout": "",
            "stderr": "Compilation timed out after 20 seconds.",
            "errors_count": 1,
            "warnings_count": 0,
            "diagnostics": []
        }

    parsed = parse_gcc_output(proc.stderr)
    exe_created = proc.returncode == 0 and os.path.isfile(exe_path) and os.access(exe_path, os.X_OK)

    if not exe_created and os.path.exists(exe_path):
        try:
            os.remove(exe_path)
        except OSError:
            pass

    errors_count = parsed["errors_count"]
    if not exe_created and errors_count == 0:
        errors_count = 1

    state = {
        "status": "compiled" if exe_created else "failed",
        "return_code": proc.returncode,
        "errors_count": errors_count,
        "warnings_count": parsed["warnings_count"],
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "diagnostics": parsed["diagnostics"],
        "duration_ms": duration_ms,
        "command": " ".join(["gcc", "-Wall", "-Wextra", "-std=c11", "-g", rel_src, "-o", rel_exe]),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    _save_compile_state(norm_name, state)

    return {
        "success": exe_created,
        "name": norm_name,
        "source_path": rel_src,
        "executable_path": rel_exe if exe_created else None,
        "command": state["command"],
        "return_code": proc.returncode,
        "duration_ms": duration_ms,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "errors_count": errors_count,
        "warnings_count": parsed["warnings_count"],
        "diagnostics": parsed["diagnostics"],
        "timestamp": state["timestamp"]
    }


def delete_custom_program(program_name: str) -> Dict[str, Any]:
    """
    Delete a user-created custom C source file and its compiled binary.
    Official built-in test programs cannot be deleted.
    """
    ok, norm_name, err = validate_program_name(program_name, allow_official=False)
    if not ok:
        raise ValueError(err)

    src_path = os.path.join(TESTS_DIR, f"{norm_name}.c")
    exe_path = os.path.join(TESTS_DIR, norm_name)

    if not os.path.isfile(src_path) and not os.path.isfile(exe_path):
        raise FileNotFoundError(f"Custom program '{norm_name}' does not exist.")

    if os.path.exists(src_path):
        os.remove(src_path)
    if os.path.exists(exe_path):
        os.remove(exe_path)

    states = _load_compile_states()
    if norm_name in states:
        del states[norm_name]
        try:
            with open(COMPILE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(states, f, indent=2)
        except Exception:
            pass

    return {
        "success": True,
        "deleted": norm_name
    }


def ensure_core_built() -> Dict[str, Any]:
    """
    Verify ./debugger, ./autodebug, and ./ldst are compiled; run 'make' if missing.
    """
    debugger_bin = os.path.join(PROJECT_ROOT, "debugger")
    autodebug_bin = os.path.join(PROJECT_ROOT, "autodebug")
    if os.path.isfile(debugger_bin) and os.access(debugger_bin, os.X_OK) and \
       os.path.isfile(autodebug_bin) and os.access(autodebug_bin, os.X_OK):
        return {"success": True, "built": False}

    make_bin = shutil.which("make")
    if not make_bin:
        return {"success": False, "error": "make utility not found."}

    proc = subprocess.run([make_bin], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30)
    return {
        "success": proc.returncode == 0,
        "built": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr
    }
