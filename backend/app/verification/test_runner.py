"""
Linux System Debugging Tool - Logical Bug Test Case Runner
Executes tests against target binaries with custom stdin and arguments,
verifies expected output and exit codes, and provides line diffs.
"""

import difflib
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import toolchain


def run_test_case(executable_path: str, args: List[str], stdin_data: str,
                  expected_output: str, expected_exit_code: int = 0,
                  working_dir: Optional[str] = None, timeout: float = 10.0) -> Dict[str, Any]:
    """
    Executes the compiled binary with provided stdin and args,
    comparing actual output against expected output.
    """
    cmd = [executable_path] + (args or [])

    start_time = time.time()
    try:
        if toolchain.is_linux or not toolchain.has_wsl:
            proc = subprocess.run(
                cmd,
                input=stdin_data,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                errors="replace"
            )
            actual_stdout = proc.stdout
            actual_stderr = proc.stderr
            actual_exit = proc.returncode
        else:
            # Run via WSL
            wsl_cwd = toolchain.to_wsl_path(working_dir) if working_dir else None
            wsl_exe = toolchain.to_wsl_path(executable_path)
            wsl_cmd = ["wsl", "-d", "Ubuntu"]
            if wsl_cwd:
                wsl_cmd.extend(["--cd", wsl_cwd])
            wsl_cmd.append("--")
            wsl_cmd.append(wsl_exe)
            wsl_cmd.extend(args or [])

            proc = subprocess.run(
                wsl_cmd,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=timeout,
                errors="replace"
            )
            actual_stdout = proc.stdout
            actual_stderr = proc.stderr
            actual_exit = proc.returncode

        duration_ms = round((time.time() - start_time) * 1000, 2)
        timed_out = False

    except subprocess.TimeoutExpired:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        timed_out = True
        actual_stdout = ""
        actual_stderr = f"Execution timed out after {timeout} seconds (suspected hang or infinite loop)."
        actual_exit = -1

    # Normalize newlines for diff comparison
    norm_expected = expected_output.replace("\r\n", "\n").strip()
    norm_actual = actual_stdout.replace("\r\n", "\n").strip()

    output_match = (norm_expected == norm_actual)
    exit_match = (actual_exit == expected_exit_code)
    passed = output_match and exit_match and not timed_out

    # Generate unified diff if outputs differ
    diff = []
    if not output_match:
        diff = list(difflib.unified_diff(
            norm_expected.splitlines(keepends=True),
            norm_actual.splitlines(keepends=True),
            fromfile="expected",
            tofile="actual"
        ))

    return {
        "passed": passed,
        "output_match": output_match,
        "exit_code_match": exit_match,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "actual_stdout": actual_stdout,
        "actual_stderr": actual_stderr,
        "actual_exit_code": actual_exit,
        "expected_exit_code": expected_exit_code,
        "diff": "".join(diff)
    }
