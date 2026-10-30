#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PASSED=0
FAILED=0
SKIPPED=0

pass() {
    echo "[PASS] $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "[FAIL] $1"
    if [ -n "${2:-}" ]; then
        echo "       Reason: $2"
    fi
    FAILED=$((FAILED + 1))
}

skip() {
    echo "[SKIP] $1"
    SKIPPED=$((SKIPPED + 1))
}

echo "LDST Self-Test"
echo "================================"
echo

# 1. Clean build without warnings
BUILD_OUT=$(make clean 2>&1 && make 2>&1 && make tests 2>&1)
BUILD_RC=$?
if [ $BUILD_RC -eq 0 ] && [ -x "./debugger" ] && [ -x "./autodebug" ] && [ -x "./ldst" ]; then
    WARN_LINES=$(echo "$BUILD_OUT" | grep -i "warning:" || true)
    if [ -n "$WARN_LINES" ]; then
        fail "Core builds without warnings" "$WARN_LINES"
    else
        pass "Core builds without warnings"
    fi
else
    fail "Core builds without warnings" "make returned $BUILD_RC: $BUILD_OUT"
fi

# 2. Normal execution via C debugger
OUT_NORM=$(./debugger ./tests/normal_test 2>&1)
if echo "$OUT_NORM" | grep -q "Termination    : Normal" && echo "$OUT_NORM" | grep -q "Exit Status    : 0" && echo "$OUT_NORM" | grep -q "No failed system call identified"; then
    pass "Normal execution (CLI ./debugger)"
else
    fail "Normal execution (CLI ./debugger)" "$OUT_NORM"
fi

# 3. ENOENT detection
OUT_ENOENT=$(./debugger ./tests/file_error 2>&1)
if echo "$OUT_ENOENT" | grep -q "Error          : ENOENT" && echo "$OUT_ENOENT" | grep -q "errno          : 2"; then
    pass "ENOENT detection (CLI ./debugger)"
else
    fail "ENOENT detection (CLI ./debugger)" "$OUT_ENOENT"
fi

# 4. EBADF detection
OUT_EBADF=$(./debugger ./tests/invalid_fd 2>&1)
if echo "$OUT_EBADF" | grep -q "Error          : EBADF" && echo "$OUT_EBADF" | grep -q "errno          : 9"; then
    pass "EBADF detection (CLI ./debugger)"
else
    fail "EBADF detection (CLI ./debugger)" "$OUT_EBADF"
fi

# 5. EACCES permission error detection
OUT_EACCES=$(./debugger ./tests/permission_error 2>&1)
if echo "$OUT_EACCES" | grep -q "Error          : EACCES" && echo "$OUT_EACCES" | grep -q "errno          : 13"; then
    pass "EACCES permission failure detection"
else
    fail "EACCES permission failure detection" "$OUT_EACCES"
fi

# 6. System-call failure (tests/system_call_error)
OUT_SCERR=$(./debugger ./tests/system_call_error 2>&1)
if echo "$OUT_SCERR" | grep -q "System Call    : read()" && echo "$OUT_SCERR" | grep -q "Error          : EBADF"; then
    pass "System-call failure detection (system_call_error)"
else
    fail "System-call failure detection (system_call_error)" "$OUT_SCERR"
fi

# 7. SIGTERM abnormal termination detection
OUT_SIGTERM=$(./debugger ./tests/abnormal_exit 2>&1)
if echo "$OUT_SIGTERM" | grep -q "Termination    : Abnormal" && echo "$OUT_SIGTERM" | grep -q "SIGTERM"; then
    pass "SIGTERM detection (CLI ./debugger)"
else
    fail "SIGTERM detection (CLI ./debugger)" "$OUT_SIGTERM"
fi

# 8. SIGSEGV detection
OUT_SIGSEGV=$(./debugger ./tests/segmentation_fault 2>&1)
if echo "$OUT_SIGSEGV" | grep -q "Termination    : Abnormal" && echo "$OUT_SIGSEGV" | grep -q "SIGSEGV"; then
    pass "SIGSEGV detection (CLI ./debugger)"
else
    fail "SIGSEGV detection (CLI ./debugger)" "$OUT_SIGSEGV"
fi

# 9. AutoDebugger normal execution (verifies loader noise filtering)
AUTO_NORM=$(./autodebug ./tests/normal_test 2>&1)
if echo "$AUTO_NORM" | grep -q "Result        : NORMAL" && echo "$AUTO_NORM" | grep -q "Exit code     : 0"; then
    pass "AutoDebugger clean execution (noise filtering)"
else
    fail "AutoDebugger clean execution (noise filtering)" "$AUTO_NORM"
fi

# 10. AutoDebugger + GDB crash backtrace
if command -v gdb >/dev/null 2>&1; then
    AUTO_SEGV=$(./autodebug ./tests/segmentation_fault 2>&1)
    if echo "$AUTO_SEGV" | grep -q "SIGSEGV" && echo "$AUTO_SEGV" | grep -q "segmentation_fault.c"; then
        pass "GDB crash backtrace analysis (CLI ./autodebug)"
    else
        fail "GDB crash backtrace analysis (CLI ./autodebug)" "$AUTO_SEGV"
    fi
else
    skip "GDB test — GDB unavailable"
fi

# 11. Interactive CLI ./ldst non-interactive exit test
LDST_OUT=$(printf "8\n" | ./ldst 2>&1)
if echo "$LDST_OUT" | grep -q "Linux System Debugging Tool closed."; then
    pass "Interactive CLI launcher (./ldst) works"
else
    fail "Interactive CLI launcher (./ldst) works" "$LDST_OUT"
fi

# 12. Comprehensive Web Backend, API, Security, Compilation & Regression Suite
PYTHON_TEST_OUT=$(python3 - <<'PYEOF'
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath("web"))
from services.security import validate_program_name
from services.compiler import save_custom_program, compile_program, delete_custom_program
from services.debugger import start_debugger_session, stop_session
from services.autodebugger import start_autodebug_session
from services.reports import list_reports, get_report, get_report_txt, delete_report
from services.interactive_debugger import (
    create_interactive_session,
    execute_debugger_action,
    get_interactive_session
)

results = []

def record(passed, name, detail=""):
    results.append((passed, name, detail))

# Test A: Directory traversal & unsafe name prevention
ok1, _, _ = validate_program_name("../../etc/passwd")
ok2, _, _ = validate_program_name("/tmp/evil")
ok3, _, _ = validate_program_name("bad;rm -rf")
ok4, _, _ = validate_program_name("normal_test", allow_official=False)
record(not ok1 and not ok2 and not ok3 and not ok4, "Security: directory traversal & shell injection rejected")

# Test B: Empty source handling
try:
    save_custom_program("selftest_empty", "   \n  ")
    record(False, "Empty source rejected cleanly", "Did not raise ValueError")
except ValueError:
    record(True, "Empty source rejected cleanly")

# Test C: Custom valid C program creation, compilation (with warning), and execution
valid_c = """#include <stdio.h>
int main(void) {
    int unused_var = 10;
    printf("Hello from custom stdout!\\n");
    fprintf(stderr, "Hello from custom stderr!\\n");
    return 0;
}
"""
comp_valid = compile_program("selftest_custom_ok", valid_c)
record(
    comp_valid.get("success") is True and comp_valid.get("warnings_count", 0) >= 1,
    "Custom C compilation & GCC warning count detection",
    str(comp_valid)
)

# Test D: Custom program stdout/stderr capture & clean debugger run
dbg_custom = start_debugger_session("selftest_custom_ok", use_trace=True, use_monitor=True, capture_output=True, async_mode=False)
record(
    dbg_custom.get("result_badge") == "SUCCESS"
    and "Hello from custom stdout!" in dbg_custom.get("program_stdout", "")
    and "Hello from custom stderr!" in dbg_custom.get("program_stderr", ""),
    "Custom program execution & real stdout/stderr capture",
    str(dbg_custom.get("result_badge"))
)

# Test E: Failed compilation removes stale executable and blocks Debug button
broken_c = """#include <stdio.h>
int main(void) {
    printf("Missing semicolon")
    return 0;
}
"""
comp_broken = compile_program("selftest_custom_ok", broken_c)
exe_exists_after_fail = os.path.exists("tests/selftest_custom_ok")
dbg_after_fail = start_debugger_session("selftest_custom_ok", async_mode=False)
record(
    comp_broken.get("success") is False
    and comp_broken.get("errors_count", 0) >= 1
    and not exe_exists_after_fail
    and dbg_after_fail.get("success") is False
    and dbg_after_fail.get("error_type") == "COMPILATION_FAILED",
    "Failed compilation removes stale binary & blocks execution",
    f"exe_exists={exe_exists_after_fail}, dbg={dbg_after_fail.get('error_type')}"
)

# Test F: Intentional compile error in tests/ does not break 'make tests'
make_rc = subprocess.run(["make", "tests"], capture_output=True).returncode
record(make_rc == 0, "Intentional custom compile error does not break project build")
delete_custom_program("selftest_custom_ok")

# Test G: Program returning non-zero exit code without syscall error
nonzero_c = """int main(void) { return 7; }\n"""
compile_program("selftest_nonzero", nonzero_c)
dbg_nz = start_debugger_session("selftest_nonzero", async_mode=False)
record(
    dbg_nz.get("exit_code") == 7 and dbg_nz.get("result_badge") == "EXIT 7",
    "Non-zero exit code (7) accurately classified (not called clean)",
    str(dbg_nz.get("result_badge"))
)
delete_custom_program("selftest_nonzero")

# Test H: Multiple failed system calls & grouping
multi_err_c = """#include <fcntl.h>
#include <unistd.h>
int main(void) {
    open("no_such_1.txt", O_RDONLY);
    open("no_such_2.txt", O_RDONLY);
    char b[4];
    read(-1, b, 4);
    return 1;
}
"""
compile_program("selftest_multi", multi_err_c)
dbg_multi = start_debugger_session("selftest_multi", async_mode=False)
sc_analysis = dbg_multi.get("syscall_analysis", {})
record(
    sc_analysis.get("relevant_failures", 0) >= 3 and len(sc_analysis.get("grouped_failures", [])) >= 2,
    "Multiple failed system calls grouped & counted accurately",
    str(sc_analysis.get("relevant_failures"))
)
delete_custom_program("selftest_multi")

# Test I: Custom segmentation fault program via AutoDebugger + GDB line attribution
segv_c = """#include <stdio.h>
int main(void) {
    int *p = 0;
    *p = 99;
    return 0;
}
"""
compile_program("selftest_segv", segv_c)
auto_segv = start_autodebug_session("selftest_segv", enable_gdb=True, async_mode=False)
record(
    auto_segv.get("result_badge") == "SIGSEGV"
    and auto_segv.get("source_evidence", {}).get("line") == 4,
    "Custom SIGSEGV crash & exact GDB source line (line 4) attribution",
    str(auto_segv.get("source_evidence"))
)
delete_custom_program("selftest_segv")

# Test J: Timeout & user stop handling on long-running process
long_c = """#define _DEFAULT_SOURCE
#include <unistd.h>
int main(void) {
    for (int i = 0; i < 100; ++i) usleep(100000);
    return 0;
}
"""
comp_long = compile_program("selftest_long", long_c)
dbg_timeout = start_debugger_session("selftest_long", timeout_sec=1.0, async_mode=False)
record(
    comp_long.get("success") is True and dbg_timeout.get("result_badge") == "TIMEOUT",
    "Execution timeout detection & child process cleanup",
    str(dbg_timeout.get("result_badge"))
)

dbg_stop_init = start_debugger_session("selftest_long", timeout_sec=15.0, async_mode=True)
sid_stop = dbg_stop_init.get("session_id")
if sid_stop:
    time.sleep(0.25)
    stop_session(sid_stop)
    time.sleep(0.45)
    rep_stopped = get_report(sid_stop)
    record(
        rep_stopped.get("result_badge") == "STOPPED",
        "User stops running debug session cleanly",
        str(rep_stopped.get("result_badge"))
    )
    delete_report(sid_stop)
else:
    record(False, "User stops running debug session cleanly", f"No session_id: {dbg_stop_init}")
if dbg_timeout.get("session_id"):
    delete_report(dbg_timeout["session_id"])
delete_custom_program("selftest_long")

# Test K: Report creation, reopening, TXT/JSON export, and deletion
sid_test = dbg_custom.get("session_id")
reopened = get_report(sid_test)
txt_exported = get_report_txt(sid_test)
del_res = delete_report(sid_test)
record(
    reopened.get("session_id") == sid_test
    and "LDST — LINUX SYSTEM DEBUGGING TOOL DIAGNOSTIC REPORT" in txt_exported
    and del_res.get("success") is True,
    "Report persistence, reopening, export, and deletion"
)

# Test M1: Interactive GDB Stepping and Local Variable Inspection (math_step)
res_m = create_interactive_session("math_step")
sid_m = res_m.get("session", {}).get("session_id")
next1 = execute_debugger_action(sid_m, "next") if sid_m else {"session": {"variables": []}}
next2 = execute_debugger_action(sid_m, "next") if sid_m else {"session": {"variables": []}}
next3 = execute_debugger_action(sid_m, "next") if sid_m else {"session": {"variables": []}}
v_map = {v["name"]: v["value"] for v in next3.get("session", {}).get("variables", [])}
if sid_m: execute_debugger_action(sid_m, "stop")
record(
    res_m.get("success") is True and v_map.get("a") == "10" and v_map.get("b") == "20" and v_map.get("c") == "30",
    "Interactive GDB: line-by-line stepping & honest variable inspection (a=10, b=20, c=30)",
    f"v_map: {v_map}"
)

# Test M2: Interactive Function Call (Step Into / Step Out, Call Stack, Arguments)
res_f = create_interactive_session("function_call")
sid_f = res_f.get("session", {}).get("session_id")
s_curr = res_f.get("session", {})
while s_curr.get("current_line") and s_curr.get("current_line") < 13 and s_curr.get("state") == "STOPPED":
    step_n = execute_debugger_action(sid_f, "next")
    s_curr = step_n.get("session", {})
into_res = execute_debugger_action(sid_f, "step_into")
s_into = into_res.get("session", {})
out_res = execute_debugger_action(sid_f, "step_out")
s_out = out_res.get("session", {})
if sid_f: execute_debugger_action(sid_f, "stop")
record(
    s_into.get("current_func") == "add"
    and len(s_into.get("call_stack", [])) >= 2
    and len(s_into.get("arguments", [])) >= 2
    and s_out.get("current_func") == "main",
    "Interactive GDB: Step Into function, inspect stack frames & arguments, Step Out to caller",
    f"into func: {s_into.get('current_func')}, out func: {s_out.get('current_func')}"
)

# Test M3: Interactive SIGSEGV Detection & Crashing Statement Attribution
res_seg = create_interactive_session("segmentation_fault")
sid_seg = res_seg.get("session", {}).get("session_id")
cont_seg = execute_debugger_action(sid_seg, "continue") if sid_seg else {"session": {}}
s_seg = cont_seg.get("session", {})
if sid_seg: execute_debugger_action(sid_seg, "stop")
record(
    s_seg.get("state") == "SIGNALED"
    and s_seg.get("signal_info", {}).get("signal_name") == "SIGSEGV"
    and s_seg.get("signal_info", {}).get("crashing_line") == 9
    and "*ptr = 42;" in s_seg.get("signal_info", {}).get("crashing_statement", ""),
    "Interactive GDB: Fatal signal (SIGSEGV) detection & exact statement (*ptr = 42;) attribution",
    f"signal: {s_seg.get('signal_info')}"
)

# Test M4: Interactive SIGFPE Arithmetic Trap Detection
res_fpe = create_interactive_session("sigfpe_test")
sid_fpe = res_fpe.get("session", {}).get("session_id")
cont_fpe = execute_debugger_action(sid_fpe, "continue") if sid_fpe else {"session": {}}
s_fpe = cont_fpe.get("session", {})
if sid_fpe: execute_debugger_action(sid_fpe, "stop")
record(
    s_fpe.get("state") == "SIGNALED"
    and s_fpe.get("signal_info", {}).get("signal_name") == "SIGFPE",
    "Interactive GDB: Hardware trap (SIGFPE) divide-by-zero detection",
    f"signal: {s_fpe.get('signal_info')}"
)

# Test M5: Interactive Non-Zero Exit Code (Not a crash)
res_nze = create_interactive_session("nonzero_exit")
sid_nze = res_nze.get("session", {}).get("session_id")
cont_nze = execute_debugger_action(sid_nze, "continue") if sid_nze else {"session": {}}
s_nze = cont_nze.get("session", {})
if sid_nze: execute_debugger_action(sid_nze, "stop")
record(
    s_nze.get("state") == "EXITED"
    and s_nze.get("exit_code") == 42
    and "Not a crash" in s_nze.get("stop_reason", ""),
    "Interactive GDB: Deliberate non-zero exit code (42) distinguished from crash",
    f"state: {s_nze.get('state')}, code: {s_nze.get('exit_code')}"
)

# Test M6: Breakpoint Insertion, Hit Verification, and Removal
res_bp = create_interactive_session("math_step")
sid_bp = res_bp.get("session", {}).get("session_id")
add_bp = execute_debugger_action(sid_bp, "add_breakpoint", {"line": 7}) if sid_bp else {"success": False}
cont_bp = execute_debugger_action(sid_bp, "continue") if sid_bp else {"session": {}}
s_hit = cont_bp.get("session", {})
bpid = add_bp.get("breakpoint", {}).get("id")
rem_bp = execute_debugger_action(sid_bp, "remove_breakpoint", {"breakpoint_id": bpid}) if bpid else {"success": False}
if sid_bp: execute_debugger_action(sid_bp, "stop")
record(
    add_bp.get("success") is True
    and s_hit.get("current_line") == 7
    and s_hit.get("stop_category") == "BREAKPOINT"
    and rem_bp.get("success") is True,
    "Interactive GDB: Breakpoint insertion at line 7, hit detection, and removal",
    f"hit line: {s_hit.get('current_line')}"
)

# Test L: Live HTTP Web Server startup & API health check on local port
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
free_port = sock.getsockname()[1]
sock.close()

env = os.environ.copy()
env["LDST_HOST"] = "127.0.0.1"
env["LDST_PORT"] = str(free_port)
srv = subprocess.Popen(
    [sys.executable, "web/app.py"],
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
http_ok = False
try:
    for _ in range(25):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{free_port}/api/health", timeout=1) as resp:
                hdata = json.loads(resp.read().decode("utf-8"))
                if resp.status == 200 and hdata.get("status") == "ok":
                    http_ok = True
                    break
        except Exception:
            time.sleep(0.1)
finally:
    srv.terminate()
    try:
        srv.wait(timeout=3)
    except Exception:
        srv.kill()

record(http_ok, "Web backend startup & /api/health HTTP endpoint check")

print(json.dumps(results))
PYEOF
)

if [ -n "$PYTHON_TEST_OUT" ]; then
    while IFS= read -r line; do
        STATUS=$(echo "$line" | cut -d'|' -f1)
        NAME=$(echo "$line" | cut -d'|' -f2)
        DETAIL=$(echo "$line" | cut -d'|' -f3-)
        if [ "$STATUS" = "PASS" ]; then
            pass "$NAME"
        else
            fail "$NAME" "$DETAIL"
        fi
    done < <(python3 -c '
import json, sys
data = json.loads(sys.argv[1])
for ok, name, detail in data:
    print(("PASS" if ok else "FAIL") + "|" + name + "|" + detail)
' "$PYTHON_TEST_OUT")
else
    fail "Python Web Backend Regression Suite" "Script produced no output"
fi

echo
echo "--------------------------------"
echo "Passed:  $PASSED"
echo "Failed:  $FAILED"
echo "Skipped: $SKIPPED"
echo "--------------------------------"

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
exit 0
