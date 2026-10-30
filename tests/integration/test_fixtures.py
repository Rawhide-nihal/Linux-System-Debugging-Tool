"""
Integration test suite for standard C test fixtures.
"""

from pathlib import Path
from backend.app.compiler.build_system import compile_project
from backend.app.compiler.diagnostics_parser import parse_compiler_output
from backend.app.verification.test_runner import run_test_case
from backend.app.verification.fix_verifier import verify_bug_fix

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_missing_semicolon_error():
    cand = FIXTURES_DIR / "compiler_errors"
    res = compile_project(str(cand), {"selected_file": "missing_semicolon.c"})
    assert res.success is False
    assert any("expected ';'" in d["message"] or "error" in d["severity"] for d in res.diagnostics)
    error_diag = next(d for d in res.diagnostics if d["severity"] == "error")
    assert error_diag["line"] in (4, 5)


def test_undeclared_variable_error():
    cand = FIXTURES_DIR / "compiler_errors"
    res = compile_project(str(cand), {"selected_file": "undeclared_var.c"})
    assert res.success is False
    assert any("undeclared" in d["message"].lower() for d in res.diagnostics)


def test_multi_file_calc_project():
    cand = FIXTURES_DIR / "multi_file_projects" / "calc_project"
    res = compile_project(str(cand), {"build_mode": "makefile"})
    assert res.success is True
    assert res.binary_path is not None
    assert Path(res.binary_path).is_file()

    # Execute binary and verify output
    run_res = run_test_case(
        executable_path=res.binary_path,
        args=[],
        stdin_data="",
        expected_output="Sum: 30, Product: 200\n",
        expected_exit_code=0,
        working_dir=str(cand)
    )
    assert run_res["passed"] is True
    assert "Sum: 30, Product: 200" in run_res["actual_stdout"]


def test_logic_boundary_verification_flow():
    cand = FIXTURES_DIR / "logical_errors"
    build_res = compile_project(str(cand), {"selected_file": "pass_fail_boundary.c", "target_name": "boundary_test"})
    assert build_res.success is True

    # 1. Run test with boundary 35 (Specification: marks >= 35 passes)
    failing_run = run_test_case(
        executable_path=build_res.binary_path,
        args=[],
        stdin_data="35\n",
        expected_output="PASS\n",
        expected_exit_code=0,
        working_dir=str(cand)
    )
    # Bug in code produces FAIL, so test fails
    assert failing_run["passed"] is False
    assert failing_run["actual_stdout"].strip() == "FAIL"
    assert len(failing_run["diff"]) > 0

    # 2. Simulated fix verification
    mock_passing_run = {
        "passed": True,
        "actual_stdout": "PASS\n",
        "actual_exit_code": 0
    }
    verification = verify_bug_fix(failing_run, mock_passing_run)
    assert verification["is_resolved"] is True
    assert "VERIFIED RESOLVED" in verification["status_summary"]
