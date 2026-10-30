"""
Interactive Source-Level GDB/MI Debugging Service for LDST.
Provides real-time interactive source-level C debugging over GDB Machine Interface (MI2).
Tracks source lines, execution state, breakpoints, call stacks, local variables,
function arguments, process signals, program stdout/stderr separation, and system call evidence.
"""

import json
import os
import queue
import re
import select
import shutil
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from .security import (
    PROJECT_ROOT,
    LOGS_DIR,
    TRACES_DIR,
    RESULTS_DIR,
    OFFICIAL_PROGRAMS,
    ensure_directories,
    get_program_paths,
)
from .compiler import (
    compile_program,
    ensure_core_built,
    get_program_source,
    _load_compile_states,
)
from .trace_parser import parse_trace_file, locate_source_evidence
from .reports import save_report

# Global interactive session registry
_INTERACTIVE_SESSIONS: Dict[str, "InteractiveGdbSession"] = {}
_INTERACTIVE_LOCK = threading.Lock()


# ============================================================================
# GDB Machine Interface (MI2) Output Parser
# ============================================================================

def _parse_mi_value(s: str, idx: int) -> Tuple[Any, int]:
    """Parse a single MI value (string, tuple, or list) starting at s[idx]."""
    while idx < len(s) and s[idx] in " \t\r\n":
        idx += 1
    if idx >= len(s):
        return None, idx
    c = s[idx]
    if c == '"':
        # Quoted string literal with escapes
        end = idx + 1
        res = []
        while end < len(s):
            if s[end] == '\\':
                end += 1
                if end < len(s):
                    esc = s[end]
                    if esc == 'n':
                        res.append('\n')
                    elif esc == 'r':
                        res.append('\r')
                    elif esc == 't':
                        res.append('\t')
                    elif esc == '"':
                        res.append('"')
                    elif esc == '\\':
                        res.append('\\')
                    else:
                        res.append(esc)
                    end += 1
            elif s[end] == '"':
                end += 1
                break
            else:
                res.append(s[end])
                end += 1
        return "".join(res), end
    elif c == '{':
        # MI Tuple: {k1="v1",k2="v2"}
        idx += 1
        obj: Dict[str, Any] = {}
        while idx < len(s):
            while idx < len(s) and s[idx] in " \t\r\n,":
                idx += 1
            if idx >= len(s) or s[idx] == '}':
                idx += 1
                break
            eq_idx = s.find("=", idx)
            if eq_idx == -1:
                break
            k = s[idx:eq_idx].strip()
            val, idx = _parse_mi_value(s, eq_idx + 1)
            obj[k] = val
        return obj, idx
    elif c == '[':
        # MI List: [{...},{...}] or ["a","b"] or [k1="v1"]
        idx += 1
        lst: List[Any] = []
        while idx < len(s):
            while idx < len(s) and s[idx] in " \t\r\n,":
                idx += 1
            if idx >= len(s) or s[idx] == ']':
                idx += 1
                break
            eq_idx = s.find("=", idx)
            next_delims = [s.find(d, idx) for d in ['"', '{', '[', ',', ']'] if s.find(d, idx) != -1]
            first_delim = min(next_delims) if next_delims else -1
            if eq_idx != -1 and (first_delim == -1 or eq_idx < first_delim):
                k = s[idx:eq_idx].strip()
                val, idx = _parse_mi_value(s, eq_idx + 1)
                lst.append({k: val})
            else:
                val, idx = _parse_mi_value(s, idx)
                lst.append(val)
        return lst, idx
    else:
        # Raw token (e.g. number, boolean, identifier)
        end = idx
        while end < len(s) and s[end] not in ",]} \t\r\n":
            end += 1
        return s[idx:end], end


def parse_mi_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a GDB/MI output line into a structured record.
    Prefix characters:
      '^' : Result record (^done, ^running, ^error, ^exit)
      '*' : Async exec record (*stopped, *running)
      '=' : Async notify record (=thread-group-started, =breakpoint-modified)
      '~' : Console stream record (escaped string)
      '&' : Log stream record
      '@' : Target stream record
    """
    line = line.strip()
    if not line:
        return None
    prefix = line[0]
    rest = line[1:]
    if prefix in ('~', '&', '@'):
        # Stream record
        val, _ = _parse_mi_value(rest, 0)
        return {"_prefix": prefix, "_type": "stream", "payload": val or rest}

    comma_idx = rest.find(",")
    if comma_idx == -1:
        record_type = rest
        payload_str = ""
    else:
        record_type = rest[:comma_idx]
        payload_str = rest[comma_idx + 1:]

    data: Dict[str, Any] = {"_prefix": prefix, "_type": record_type}
    idx = 0
    s = payload_str
    while idx < len(s):
        while idx < len(s) and s[idx] in " \t\r\n,":
            idx += 1
        if idx >= len(s):
            break
        eq_idx = s.find("=", idx)
        if eq_idx == -1:
            break
        k = s[idx:eq_idx].strip()
        val, idx = _parse_mi_value(s, eq_idx + 1)
        data[k] = val
    return data


# ============================================================================
# Interactive GDB Session Controller
# ============================================================================

class InteractiveGdbSession:
    """
    Manages an active GDB/MI session attached to a compiled C target.
    Controls execution stepping (Next, Step Into, Step Out, Continue),
    breakpoints, stack navigation, and inspects variables honestly from GDB.
    """

    def __init__(self, session_id: str, program_name: str):
        self.session_id = session_id
        self.program_name = program_name
        self.norm_name, self.src_path, self.exe_path = get_program_paths(program_name)

        self.state = "NOT_STARTED"
        self.pid: Optional[int] = None
        self.exit_code: Optional[int] = None
        self.current_file = f"tests/{self.norm_name}.c"
        self.current_line: Optional[int] = None
        self.current_func: Optional[str] = None
        self.current_frame_id: int = 0
        self.stop_reason: str = "Initialized"
        self.stop_category: str = "INITIALIZED"

        # Breakpoints: dict of id -> {id, line, file, enabled}
        self.breakpoints: Dict[int, Dict[str, Any]] = {}
        self.bp_next_id = 1

        # Execution evidence
        self.variables: List[Dict[str, Any]] = []
        self.arguments: List[Dict[str, Any]] = []
        self.call_stack: List[Dict[str, Any]] = []
        self.timeline: List[Dict[str, Any]] = []
        self.signal_info: Optional[Dict[str, Any]] = None
        self.syscall_evidence: Dict[str, Any] = {}

        # Log paths
        self.stdout_path = os.path.join(LOGS_DIR, f"interactive_stdout_{self.session_id}.log")
        self.stderr_path = os.path.join(LOGS_DIR, f"interactive_stderr_{self.session_id}.log")
        self.trace_path = os.path.join(TRACES_DIR, f"interactive_trace_{self.session_id}.txt")

        # Subprocess & thread-safe reader queue
        self.proc: Optional[subprocess.Popen] = None
        self.queue: queue.Queue = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.last_active = time.time()
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None

        # Source code lines cached
        self.source_code = ""
        self.source_lines: List[str] = []
        if os.path.isfile(self.src_path):
            with open(self.src_path, "r", encoding="utf-8", errors="replace") as f:
                self.source_code = f.read()
            self.source_lines = self.source_code.splitlines()

    def _add_timeline(self, event: str, description: str, line: Optional[int] = None, func: Optional[str] = None):
        """Append an entry to the debugging timeline."""
        now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.timeline.append({
            "timestamp": now_str,
            "event": event,
            "description": description,
            "line": line if line is not None else self.current_line,
            "func": func or self.current_func or "main"
        })

    def _reader_loop(self):
        """Dedicated background reader thread that drains GDB stdout without pipe blocking."""
        if not self.proc or not self.proc.stdout:
            return
        try:
            for raw_line in iter(self.proc.stdout.readline, ''):
                if not raw_line:
                    break
                self.queue.put(raw_line)
        except Exception:
            pass
        finally:
            self.queue.put(None)  # Sentinel indicating EOF

    def _send_command(self, cmd: str):
        """Send a raw command to GDB stdin."""
        if not self.proc or self.proc.poll() is not None or not self.proc.stdin:
            raise RuntimeError("GDB process is not running.")
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()
        self.last_active = time.time()

    def _read_until_prompt(self, wait_for_stopped: bool = False, timeout: float = 6.0) -> List[str]:
        """
        Read lines from GDB until the prompt `(gdb)` is received.
        If wait_for_stopped is True, continue until both `*stopped` and its trailing `(gdb)` are read.
        """
        lines: List[str] = []
        saw_stopped = False
        start_time = time.time()

        while True:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                # Timeout occurred; attempt to interrupt inferior
                if wait_for_stopped and not saw_stopped and self.proc and self.proc.poll() is None:
                    try:
                        self.proc.send_signal(signal.SIGINT)
                    except Exception:
                        pass
                break

            try:
                line = self.queue.get(timeout=min(0.2, max(0.01, remaining)))
            except queue.Empty:
                continue

            if line is None:  # EOF
                break

            stripped = line.strip()
            lines.append(stripped)

            if stripped.startswith("*stopped"):
                saw_stopped = True

            if stripped == "(gdb)":
                if wait_for_stopped:
                    if saw_stopped:
                        break
                else:
                    break

        return lines

    def _read_program_output(self) -> Dict[str, str]:
        """Read target program's actual stdout and stderr streams cleanly."""
        out_text = ""
        err_text = ""
        if os.path.isfile(self.stdout_path):
            try:
                with open(self.stdout_path, "r", encoding="utf-8", errors="replace") as f:
                    out_text = f.read()
            except Exception:
                pass
        if os.path.isfile(self.stderr_path):
            try:
                with open(self.stderr_path, "r", encoding="utf-8", errors="replace") as f:
                    err_text = f.read()
            except Exception:
                pass
        return {"stdout": out_text, "stderr": err_text}

    def _query_frame_variables(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Query GDB for local variables and arguments at the currently selected frame."""
        variables: List[Dict[str, Any]] = []
        arguments: List[Dict[str, Any]] = []

        if not self.proc or self.proc.poll() is not None or self.state not in ("STOPPED", "SIGNALED"):
            return variables, arguments

        try:
            # Query variables (simple values gives name, type, value)
            self._send_command("-stack-list-variables --simple-values")
            v_lines = self._read_until_prompt(wait_for_stopped=False, timeout=1.5)
            for line in v_lines:
                if line.startswith("^done"):
                    rec = parse_mi_line(line)
                    raw_vars = rec.get("variables", []) if rec else []
                    for v in raw_vars:
                        if isinstance(v, dict):
                            val = v.get("value")
                            vtype = v.get("type", "unknown")
                            if val is None or val == "":
                                val = "<not available>"
                            elif val in ("<optimized out>", "<out of scope>"):
                                val = val
                            elif vtype.endswith("*") and (val == "0x0" or "0x00000000" in val):
                                val = f"{val} (NULL)"
                            variables.append({
                                "name": v.get("name", "anon"),
                                "type": vtype,
                                "value": val,
                                "status": "valid" if val not in ("<not available>", "<optimized out>") else "unavailable"
                            })
        except Exception:
            pass

        try:
            # Query arguments
            self._send_command("-stack-list-arguments 1 0 0")
            a_lines = self._read_until_prompt(wait_for_stopped=False, timeout=1.5)
            for line in a_lines:
                if line.startswith("^done"):
                    rec = parse_mi_line(line)
                    stack_args = rec.get("stack-args", []) if rec else []
                    if stack_args and isinstance(stack_args, list):
                        first_frame = stack_args[0]
                        if isinstance(first_frame, dict):
                            frame_args = first_frame.get("frame", {}).get("args", [])
                            for a in frame_args:
                                if isinstance(a, dict):
                                    arguments.append({
                                        "name": a.get("name", ""),
                                        "value": a.get("value", "<not available>"),
                                        "type": a.get("type", "")
                                    })
        except Exception:
            pass

        return variables, arguments

    def _query_call_stack(self) -> List[Dict[str, Any]]:
        """Query GDB for complete stack backtrace frames."""
        frames: List[Dict[str, Any]] = []
        if not self.proc or self.proc.poll() is not None or self.state not in ("STOPPED", "SIGNALED"):
            return frames

        try:
            self._send_command("-stack-list-frames")
            lines = self._read_until_prompt(wait_for_stopped=False, timeout=1.5)
            for line in lines:
                if line.startswith("^done"):
                    rec = parse_mi_line(line)
                    stack_raw = rec.get("stack", []) if rec else []
                    for item in stack_raw:
                        f_dict = item.get("frame", item) if isinstance(item, dict) else {}
                        lvl = int(f_dict.get("level", len(frames)))
                        fline = int(f_dict.get("line", 0)) if f_dict.get("line") else None
                        fpath = f_dict.get("file", "")
                        # Relativize if inside project
                        if fpath and fpath.startswith("/"):
                            if fpath.startswith(PROJECT_ROOT):
                                fpath = os.path.relpath(fpath, PROJECT_ROOT)
                        frames.append({
                            "level": lvl,
                            "func": f_dict.get("func", "??"),
                            "file": fpath,
                            "line": fline,
                            "addr": f_dict.get("addr", ""),
                            "is_current": (lvl == self.current_frame_id)
                        })
        except Exception:
            pass

        return frames

    def _process_stopped_record(self, lines: List[str]):
        """Parse *stopped notification from GDB and update session state."""
        stopped_rec: Optional[Dict[str, Any]] = None
        for line in lines:
            if line.startswith("=thread-group-started"):
                rec = parse_mi_line(line)
                if rec and rec.get("pid"):
                    try:
                        self.pid = int(rec["pid"])
                    except ValueError:
                        pass
            if line.startswith("*stopped"):
                stopped_rec = parse_mi_line(line)

        if not stopped_rec:
            return

        reason = stopped_rec.get("reason", "")
        frame = stopped_rec.get("frame", {})

        # Extract current location
        if frame and isinstance(frame, dict):
            if frame.get("line"):
                try:
                    self.current_line = int(frame["line"])
                except ValueError:
                    pass
            if frame.get("func"):
                self.current_func = frame["func"]
            if frame.get("file"):
                fpath = frame["file"]
                if fpath.startswith("/") and fpath.startswith(PROJECT_ROOT):
                    fpath = os.path.relpath(fpath, PROJECT_ROOT)
                self.current_file = fpath

        # Handle termination/signal/breakpoint/step reasons
        if reason == "exited-normally":
            self.state = "EXITED"
            self.exit_code = 0
            self.stop_category = "EXIT"
            self.stop_reason = "Program exited normally with code 0"
            self.completed_at = datetime.now(timezone.utc).isoformat()
            self._add_timeline("PROGRAM_EXITED", self.stop_reason)

        elif reason == "exited":
            self.state = "EXITED"
            code_str = stopped_rec.get("exit-code", "1")
            try:
                self.exit_code = int(code_str, 8) if code_str.startswith("0") and len(code_str) > 1 else int(code_str)
            except ValueError:
                self.exit_code = 1
            self.stop_category = "EXIT"
            self.stop_reason = f"Program completed execution and exited with non-zero status code {self.exit_code} (Not a crash)"
            self.completed_at = datetime.now(timezone.utc).isoformat()
            self._add_timeline("PROGRAM_EXITED", self.stop_reason)

        elif reason == "signal-received":
            sig_name = stopped_rec.get("signal-name", "SIGUNKNOWN")
            sig_meaning = stopped_rec.get("signal-meaning", "Fatal signal encountered")
            self.state = "SIGNALED"
            self.stop_category = "SIGNAL"
            self.stop_reason = f"Fatal Signal Encountered: {sig_name} ({sig_meaning})"
            self.completed_at = datetime.now(timezone.utc).isoformat()

            # Identify fatal statement
            stmt = ""
            if self.current_line and 1 <= self.current_line <= len(self.source_lines):
                stmt = self.source_lines[self.current_line - 1].strip()

            self.signal_info = {
                "signal_name": sig_name,
                "signal_meaning": sig_meaning,
                "crashing_file": self.current_file,
                "crashing_line": self.current_line,
                "crashing_func": self.current_func,
                "crashing_statement": stmt,
                "summary": f"Process terminated abnormally due to {sig_name}: {sig_meaning} at {self.current_file}:{self.current_line}"
            }
            self._add_timeline("SIGNAL_RECEIVED", self.stop_reason, self.current_line, self.current_func)

        elif reason == "breakpoint-hit":
            bkptno = stopped_rec.get("bkptno", "?")
            self.state = "STOPPED"
            self.stop_category = "BREAKPOINT"
            self.stop_reason = f"Hit breakpoint #{bkptno} at {self.current_func or 'main'}() [line {self.current_line}]"
            self._add_timeline("BREAKPOINT_HIT", self.stop_reason, self.current_line, self.current_func)

        elif reason in ("end-stepping-range", "function-finished"):
            self.state = "STOPPED"
            self.stop_category = "STEP_COMPLETED"
            action_name = "Step Out" if reason == "function-finished" else "Step"
            self.stop_reason = f"{action_name} completed, stopped at line {self.current_line} in {self.current_func or 'main'}()"
            self._add_timeline("STEP_COMPLETED", self.stop_reason, self.current_line, self.current_func)

        else:
            self.state = "STOPPED"
            self.stop_category = "STOPPED"
            self.stop_reason = f"Stopped: {reason or 'Debugger pause'}"
            self._add_timeline("STOPPED", self.stop_reason, self.current_line, self.current_func)

        # Refresh variables and call stack
        self.variables, self.arguments = self._query_frame_variables()
        self.call_stack = self._query_call_stack()

    # ========================================================================
    # Public Controller Actions
    # ========================================================================

    def start(self, initial_breakpoints: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Compile target with -Wall -Wextra -std=c11 -g -O0, run quick strace correlation pass,
        launch GDB/MI, insert breakpoint at main(), and stop at the first executable statement.
        """
        with self.lock:
            ensure_directories()
            core_check = ensure_core_built()
            if not core_check.get("success"):
                self.state = "ERROR"
                self.stop_reason = "Core LDST build failed"
                return {"success": False, "error_type": "CORE_BUILD_FAILED", "error": core_check.get("error")}

            # 1. Compile target program strictly with -g -O0
            self.state = "COMPILING"
            comp_res = compile_program(self.norm_name)
            if not comp_res.get("success"):
                self.state = "ERROR"
                self.stop_reason = "Compilation failed with errors"
                self._add_timeline("COMPILATION_FAILED", "Target failed to compile")
                return {
                    "success": False,
                    "error_type": "COMPILATION_FAILED",
                    "error": comp_res.get("output", "Compilation failed"),
                    "compilation": comp_res
                }

            # 2. Run quick non-interactive strace pass to collect real syscall evidence
            try:
                strace_cmd = [
                    "strace",
                    "-o", self.trace_path,
                    "-s", "256",
                    "-f",
                    self.exe_path
                ]
                subprocess.run(strace_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3.0)
                if os.path.isfile(self.trace_path):
                    self.syscall_evidence = parse_trace_file(self.trace_path)
            except Exception:
                self.syscall_evidence = {"available": False, "total_syscalls": 0}

            # 3. Clean any existing log files
            for p in (self.stdout_path, self.stderr_path):
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            # 4. Spawn GDB with MI2 interface
            gdb_cmd = ["gdb", "--interpreter=mi2", "-q", "-nx", self.exe_path]
            try:
                self.proc = subprocess.Popen(
                    gdb_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            except FileNotFoundError:
                self.state = "ERROR"
                self.stop_reason = "GDB is not installed on this system"
                return {"success": False, "error_type": "GDB_NOT_FOUND", "error": "GDB binary not found in PATH."}

            self.state = "STARTING"
            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()

            # Read initial startup greeting from GDB
            self._read_until_prompt(wait_for_stopped=False, timeout=2.0)

            # Redirect target stdout and stderr cleanly
            self._send_command(f"-exec-arguments > {self.stdout_path} 2> {self.stderr_path}")
            self._read_until_prompt(wait_for_stopped=False, timeout=1.0)

            # Break at main()
            self._send_command("-break-insert main")
            bp_lines = self._read_until_prompt(wait_for_stopped=False, timeout=1.5)
            main_bp_id = 1
            for bpl in bp_lines:
                if bpl.startswith("^done"):
                    rec = parse_mi_line(bpl)
                    bkpt = rec.get("bkpt", {}) if rec else {}
                    if bkpt.get("number"):
                        try:
                            main_bp_id = int(bkpt["number"])
                        except ValueError:
                            pass
                    line_num = int(bkpt.get("line", 1)) if bkpt.get("line") else 1
                    self.breakpoints[main_bp_id] = {
                        "id": main_bp_id,
                        "line": line_num,
                        "file": self.current_file,
                        "func": "main",
                        "enabled": True
                    }

            # Set any user requested initial breakpoints
            if initial_breakpoints:
                for line_no in initial_breakpoints:
                    if line_no != self.breakpoints.get(main_bp_id, {}).get("line"):
                        self.add_breakpoint(line_no)

            # 5. Launch execution to initial breakpoint
            self._send_command("-exec-run")
            run_lines = self._read_until_prompt(wait_for_stopped=True, timeout=4.0)
            self._process_stopped_record(run_lines)

            self._add_timeline(
                "SESSION_STARTED",
                f"Interactive debugging session started for {self.norm_name} (PID: {self.pid or 'active'})"
            )

            return {"success": True, "session": self.get_snapshot()}

    def step_next(self) -> Dict[str, Any]:
        """NEXT: Execute current source statement and stop at the next source line without entering functions."""
        with self.lock:
            if self.state != "STOPPED":
                return {"success": False, "error": f"Cannot step when debugger is in '{self.state}' state."}

            self.state = "RUNNING"
            self._send_command("-exec-next")
            lines = self._read_until_prompt(wait_for_stopped=True, timeout=5.0)
            self._process_stopped_record(lines)
            return {"success": True, "session": self.get_snapshot()}

    def step_into(self) -> Dict[str, Any]:
        """STEP INTO: If current statement calls a function, enter that function."""
        with self.lock:
            if self.state != "STOPPED":
                return {"success": False, "error": f"Cannot step into when debugger is in '{self.state}' state."}

            self.state = "RUNNING"
            self._send_command("-exec-step")
            lines = self._read_until_prompt(wait_for_stopped=True, timeout=5.0)
            self._process_stopped_record(lines)
            return {"success": True, "session": self.get_snapshot()}

    def step_out(self) -> Dict[str, Any]:
        """STEP OUT: Finish current function and return to its caller."""
        with self.lock:
            if self.state != "STOPPED":
                return {"success": False, "error": f"Cannot step out when debugger is in '{self.state}' state."}

            self.state = "RUNNING"
            self._send_command("-exec-finish")
            lines = self._read_until_prompt(wait_for_stopped=True, timeout=5.0)
            self._process_stopped_record(lines)
            return {"success": True, "session": self.get_snapshot()}

    def step_continue(self) -> Dict[str, Any]:
        """CONTINUE: Resume execution until breakpoint, signal, or program termination."""
        with self.lock:
            if self.state != "STOPPED":
                return {"success": False, "error": f"Cannot continue when debugger is in '{self.state}' state."}

            self.state = "RUNNING"
            self._send_command("-exec-continue")
            lines = self._read_until_prompt(wait_for_stopped=True, timeout=8.0)
            self._process_stopped_record(lines)
            return {"success": True, "session": self.get_snapshot()}

    def add_breakpoint(self, line: int) -> Dict[str, Any]:
        """Set a breakpoint on a specific line of the program."""
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                return {"success": False, "error": "Debugger is not active."}

            # Check if breakpoint already exists on this line
            for bpid, binfo in self.breakpoints.items():
                if binfo.get("line") == line:
                    return {"success": True, "breakpoint": binfo, "message": "Breakpoint already exists."}

            loc = f"{self.norm_name}.c:{line}"
            self._send_command(f"-break-insert {loc}")
            lines = self._read_until_prompt(wait_for_stopped=False, timeout=2.0)
            for l in lines:
                if l.startswith("^done"):
                    rec = parse_mi_line(l)
                    bkpt = rec.get("bkpt", {}) if rec else {}
                    bno = int(bkpt.get("number", self.bp_next_id))
                    actual_line = int(bkpt.get("line", line)) if bkpt.get("line") else line
                    bp_data = {
                        "id": bno,
                        "line": actual_line,
                        "file": self.current_file,
                        "func": bkpt.get("func", ""),
                        "enabled": True
                    }
                    self.breakpoints[bno] = bp_data
                    self._add_timeline("BREAKPOINT_ADDED", f"Breakpoint #{bno} set at line {actual_line}", actual_line)
                    return {"success": True, "breakpoint": bp_data}
                elif l.startswith("^error"):
                    rec = parse_mi_line(l)
                    msg = rec.get("msg", "Could not set breakpoint") if rec else "Breakpoint error"
                    return {"success": False, "error": msg}

            return {"success": False, "error": "Timed out setting breakpoint"}

    def remove_breakpoint(self, breakpoint_id: int) -> Dict[str, Any]:
        """Remove a breakpoint by its GDB breakpoint number."""
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                return {"success": False, "error": "Debugger is not active."}

            if breakpoint_id not in self.breakpoints:
                return {"success": False, "error": f"Breakpoint #{breakpoint_id} not found."}

            old_line = self.breakpoints[breakpoint_id].get("line")
            self._send_command(f"-break-delete {breakpoint_id}")
            self._read_until_prompt(wait_for_stopped=False, timeout=1.5)
            del self.breakpoints[breakpoint_id]
            self._add_timeline("BREAKPOINT_REMOVED", f"Breakpoint #{breakpoint_id} removed", old_line)
            return {"success": True, "message": f"Breakpoint #{breakpoint_id} removed."}

    def select_frame(self, frame_level: int) -> Dict[str, Any]:
        """Select a stack frame in the call stack and inspect variables at that depth."""
        with self.lock:
            if self.state not in ("STOPPED", "SIGNALED"):
                return {"success": False, "error": "Can only select frame when debugger is stopped."}

            self._send_command(f"-stack-select-frame {frame_level}")
            self._read_until_prompt(wait_for_stopped=False, timeout=1.5)
            self.current_frame_id = frame_level

            # Re-query variables for the newly selected frame
            self.variables, self.arguments = self._query_frame_variables()
            for f in self.call_stack:
                f["is_current"] = (f.get("level") == frame_level)

            self._add_timeline("FRAME_SELECTED", f"Selected stack frame #{frame_level}")
            return {"success": True, "session": self.get_snapshot()}

    def stop(self) -> Dict[str, Any]:
        """Cleanly terminate the active debugging session and all inferior child processes."""
        with self.lock:
            if self.state in ("EXITED", "USER_TERMINATED"):
                return {"success": True, "message": "Session already completed."}

            self.state = "USER_TERMINATED"
            self.stop_category = "INTERRUPT"
            self.stop_reason = "Debugging session stopped by user"
            self.completed_at = datetime.now(timezone.utc).isoformat()
            self._add_timeline("SESSION_STOPPED", "Debugging session manually stopped by user")

            if self.proc:
                try:
                    self._send_command("-gdb-exit")
                    self.proc.wait(timeout=0.5)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass

            # If inferior PID is still alive, terminate it safely
            if self.pid:
                try:
                    os.kill(self.pid, signal.SIGKILL)
                except Exception:
                    pass

            return {"success": True, "session": self.get_snapshot()}

    def get_snapshot(self) -> Dict[str, Any]:
        """Return a structured snapshot of the interactive session for JSON response."""
        output = self._read_program_output()
        return {
            "session_id": self.session_id,
            "program": self.norm_name,
            "state": self.state,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "current_file": self.current_file,
            "current_line": self.current_line,
            "current_func": self.current_func or "main",
            "current_frame_id": self.current_frame_id,
            "stop_reason": self.stop_reason,
            "stop_category": self.stop_category,
            "breakpoints": list(self.breakpoints.values()),
            "variables": self.variables,
            "arguments": self.arguments,
            "call_stack": self.call_stack,
            "program_output": output,
            "timeline": self.timeline,
            "signal_info": self.signal_info,
            "syscall_evidence": self.syscall_evidence,
            "source": {
                "name": f"{self.norm_name}.c",
                "code": self.source_code,
                "lines": self.source_lines,
                "total_lines": len(self.source_lines)
            },
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }

    def save_diagnostic_report(self) -> Dict[str, Any]:
        """Persist structured report to reports/ directory for historical viewing."""
        snapshot = self.get_snapshot()
        rep_data = {
            "session_id": self.session_id,
            "program": self.norm_name,
            "analysis_type": "Interactive Debugger",
            "mode": "Interactive GDB",
            "state": self.state,
            "exit_code": self.exit_code,
            "pid": self.pid,
            "result_badge": "CRASH" if self.state == "SIGNALED" else ("EXIT 0" if self.exit_code == 0 else f"EXIT {self.exit_code}"),
            "badge_tone": "danger" if self.state == "SIGNALED" else ("success" if self.exit_code == 0 else "warning"),
            "overall_status": self.stop_reason,
            "illustration_type": "error" if self.state == "SIGNALED" else ("success" if self.exit_code == 0 else "empty"),
            "start_time": self.created_at,
            "end_time": self.completed_at or datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": int((time.time() - self.last_active) * 1000),
            "command": f"gdb --interpreter=mi2 -q -nx tests/{self.norm_name}",
            "stdout": snapshot["program_output"]["stdout"],
            "stderr": snapshot["program_output"]["stderr"],
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "trace_path": self.trace_path,
            "strace": self.syscall_evidence,
            "gdb": {
                "available": True,
                "crash_detected": (self.state == "SIGNALED"),
                "signal_name": (self.signal_info or {}).get("signal_name"),
                "signal_meaning": (self.signal_info or {}).get("signal_meaning"),
                "fault_address": "",
                "crashing_file": (self.signal_info or {}).get("crashing_file"),
                "crashing_line": (self.signal_info or {}).get("crashing_line"),
                "crashing_func": (self.signal_info or {}).get("crashing_func"),
                "crashing_statement": (self.signal_info or {}).get("crashing_statement"),
                "frames": self.call_stack,
                "raw_output": ""
            },
            "variables": self.variables,
            "timeline": self.timeline,
            "source_evidence": [{
                "line_number": self.current_line,
                "code": self.source_lines[self.current_line - 1] if self.current_line and 1 <= self.current_line <= len(self.source_lines) else "",
                "evidence_type": "Interactive Execution Position",
                "detail": self.stop_reason
            }] if self.current_line else []
        }
        return save_report(rep_data)


# ============================================================================
# Session Manager Helper Functions
# ============================================================================

def create_interactive_session(program_name: str, initial_breakpoints: Optional[List[int]] = None) -> Dict[str, Any]:
    """Start and register a new interactive debugging session."""
    session_id = f"gdb_{uuid.uuid4().hex[:12]}"
    session = InteractiveGdbSession(session_id, program_name)
    with _INTERACTIVE_LOCK:
        _INTERACTIVE_SESSIONS[session_id] = session

    start_res = session.start(initial_breakpoints)
    return start_res


def get_interactive_session(session_id: str) -> Optional[InteractiveGdbSession]:
    """Retrieve an active interactive session by ID."""
    with _INTERACTIVE_LOCK:
        return _INTERACTIVE_SESSIONS.get(session_id)


def execute_debugger_action(session_id: str, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute an action (next, step_into, step_out, continue, breakpoint, stop) on a session."""
    session = get_interactive_session(session_id)
    if not session:
        return {"success": False, "error": f"Interactive session '{session_id}' not found."}

    params = params or {}
    if action == "next":
        return session.step_next()
    elif action == "step_into":
        return session.step_into()
    elif action == "step_out":
        return session.step_out()
    elif action == "continue":
        return session.step_continue()
    elif action == "add_breakpoint":
        line = int(params.get("line", 0))
        if line <= 0:
            return {"success": False, "error": "Invalid line number for breakpoint."}
        return session.add_breakpoint(line)
    elif action == "remove_breakpoint":
        bpid = int(params.get("breakpoint_id", 0))
        return session.remove_breakpoint(bpid)
    elif action == "select_frame":
        frame_level = int(params.get("frame", 0))
        return session.select_frame(frame_level)
    elif action == "stop":
        return session.stop()
    elif action == "save_report":
        rep = session.save_diagnostic_report()
        return {"success": True, "report": rep}
    elif action == "get_state":
        return {"success": True, "session": session.get_snapshot()}
    else:
        return {"success": False, "error": f"Unknown debugger action '{action}'."}
