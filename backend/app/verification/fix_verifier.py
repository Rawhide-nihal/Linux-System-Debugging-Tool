"""
Linux System Debugging Tool - Bug Fix Verification Engine
Compares baseline failure symptoms with post-patch execution results to verify fixes.
"""

from typing import Dict, Any


def verify_bug_fix(previous_run: Dict[str, Any], current_run: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates whether a bug fix successfully resolved the observed problem:
    - Previous exit status vs Current exit status
    - Previous crash vs Current crash
    - Previous test pass/fail vs Current test pass/fail
    """
    prev_passed = previous_run.get("passed", False)
    curr_passed = current_run.get("passed", False)

    prev_exit = previous_run.get("actual_exit_code")
    curr_exit = current_run.get("actual_exit_code")

    prev_crash = previous_run.get("signal") or previous_run.get("timed_out")
    curr_crash = current_run.get("signal") or current_run.get("timed_out")

    is_resolved = False
    status_summary = ""

    if not prev_passed and curr_passed:
        is_resolved = True
        status_summary = "VERIFIED RESOLVED: Test case passed with matching output and expected exit code."
    elif prev_crash and not curr_crash and curr_exit == 0:
        is_resolved = True
        status_summary = "VERIFIED RESOLVED: Runtime crash eliminated; process completed cleanly."
    elif not curr_passed:
        is_resolved = False
        status_summary = "UNRESOLVED: Current execution did not satisfy expected behavior."
    else:
        is_resolved = True
        status_summary = "Clean execution verified."

    return {
        "is_resolved": is_resolved,
        "status_summary": status_summary,
        "previous_exit_code": prev_exit,
        "current_exit_code": curr_exit,
        "previous_passed": prev_passed,
        "current_passed": curr_passed,
        "previous_output": previous_run.get("actual_stdout", ""),
        "current_output": current_run.get("actual_stdout", "")
    }
