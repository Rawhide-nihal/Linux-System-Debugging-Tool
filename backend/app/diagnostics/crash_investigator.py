"""
Linux System Debugging Tool - Crash & Runtime Failure Investigator
Diagnoses segmentation faults, division by zero, aborted assertions, and signal terminations.
"""

from typing import Dict, Any, List, Optional


def investigate_crash(signal_name: str, stopped_data: Dict[str, Any],
                      source_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Performs forensic analysis on a crash stop event using GDB state and source code.
    """
    fault_file = stopped_data.get("file")
    fault_line = stopped_data.get("line")
    fault_func = stopped_data.get("func")
    variables = stopped_data.get("variables", [])
    call_stack = stopped_data.get("call_stack", [])

    investigation = {
        "signal": signal_name,
        "category": "RUNTIME_CRASH",
        "fault_location": {
            "file": fault_file,
            "line": fault_line,
            "function": fault_func
        },
        "likely_cause": "",
        "confidence": "HIGH",
        "evidence": [],
        "suggested_action": "",
        "source_snippet": ""
    }

    # Extract source line snippet if available
    if source_code and fault_line is not None:
        lines = source_code.splitlines()
        if 1 <= fault_line <= len(lines):
            investigation["source_snippet"] = lines[fault_line - 1].strip()

    snippet = investigation["source_snippet"]

    if signal_name == "SIGSEGV":
        # Check if any pointer in variables is NULL or 0x0
        null_ptrs = [v for v in variables if "NULL" in str(v.get("value", "")) or v.get("value") == "0x0"]
        if null_ptrs:
            ptr_names = ", ".join([v["name"] for v in null_ptrs])
            investigation["likely_cause"] = f"Null pointer dereference: Pointer variable(s) '{ptr_names}' held NULL (0x0) address when accessed."
            investigation["confidence"] = "VERY HIGH"
            investigation["evidence"].append(f"Variables with NULL value at crash: {ptr_names}")
            investigation["suggested_action"] = f"Add a NULL check before dereferencing: `if ({ptr_names} != NULL) {{ ... }}`"
        elif "->" in snippet or "*" in snippet:
            investigation["likely_cause"] = "Invalid memory address dereference (unmapped or uninitialized pointer)."
            investigation["evidence"].append(f"Faulting source line: {snippet}")
            investigation["suggested_action"] = "Verify pointer allocation with malloc() and validate initialization before member access."
        else:
            investigation["likely_cause"] = "Segmentation fault caused by out-of-bounds array access or stack memory corruption."
            investigation["suggested_action"] = "Inspect array indices and buffer bounds leading up to the crash."

    elif signal_name == "SIGFPE":
        zero_vars = [v for v in variables if str(v.get("value")) in ("0", "0.0")]
        if "/" in snippet or "%" in snippet:
            investigation["likely_cause"] = "Arithmetic Exception: Integer division or modulo by zero."
            investigation["confidence"] = "VERY HIGH"
            if zero_vars:
                z_names = ", ".join([v["name"] for v in zero_vars])
                investigation["evidence"].append(f"Variables holding zero at crash: {z_names}")
            investigation["suggested_action"] = "Verify that the divisor is not zero before performing division or modulo operations."
        else:
            investigation["likely_cause"] = "Floating point exception or arithmetic overflow trap."
            investigation["suggested_action"] = "Inspect numeric ranges and floating-point computations."

    elif signal_name == "SIGABRT":
        investigation["likely_cause"] = "Program aborted via abort() or failed assertion (assert)."
        investigation["suggested_action"] = "Examine the failing assertion condition in the call stack."

    else:
        investigation["likely_cause"] = f"Process terminated abnormally due to signal {signal_name}."
        investigation["suggested_action"] = "Review signal handlers and external process events."

    return investigation
