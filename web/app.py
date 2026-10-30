#!/usr/bin/env python3
"""
LDST — Linux System Debugging Tool
Local Web Application Backend (127.0.0.1:5000)

Provides REST APIs and serves the browser GUI on top of the real LDST C debugging
engine (./debugger, ./autodebug), GCC, strace, /proc, and GDB.
Uses Flask when installed, with a built-in standard-library HTTP/WSGI fallback
so the local server starts reliably even in restricted/offline environments.
"""

import json
import mimetypes
import os
import socket
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

# Ensure web/ directory is on sys.path
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from services.security import check_environment, ensure_directories
from services.compiler import (
    list_programs,
    get_program_source,
    save_custom_program,
    compile_program,
    delete_custom_program,
    ensure_core_built,
)
from services.debugger import (
    start_debugger_session,
    get_session_status,
    stop_session,
    get_active_sessions_summary,
)
from services.interactive_debugger import (
    create_interactive_session,
    get_interactive_session,
    execute_debugger_action,
)
from services.autodebugger import start_autodebug_session
from services.process_monitor import get_system_proc_overview
from services.reports import (
    list_reports,
    get_report,
    get_report_txt,
    delete_report,
)

TEMPLATES_DIR = os.path.join(WEB_DIR, "templates")
STATIC_DIR = os.path.join(WEB_DIR, "static")


def _read_template(template_name: str) -> str:
    tpath = os.path.join(TEMPLATES_DIR, template_name)
    with open(tpath, "r", encoding="utf-8") as f:
        return f.read()


# =====================================================================
# Core Route Controller Logic (shared by Flask and stdlib HTTP server)
# =====================================================================

def api_health_data():
    env = check_environment()
    return 200, {
        "status": "ok",
        "service": "LDST Web Backend",
        "environment": env
    }


def api_dashboard_data():
    progs = list_programs()
    reports = list_reports()
    active_sessions = get_active_sessions_summary()
    env = check_environment()
    return 200, {
        "stats": {
            "builtin_tests": len(progs["builtin"]),
            "custom_programs": len(progs["custom"]),
            "total_analyses": len(reports),
            "active_processes": len(active_sessions)
        },
        "recent_analyses": reports[:15],
        "active_sessions": active_sessions,
        "environment": env
    }


def api_list_programs_data():
    return 200, list_programs()


def api_get_program_data(name: str):
    try:
        data = get_program_source(name)
        return 200, data
    except ValueError as exc:
        return 400, {"error": str(exc), "error_type": "VALIDATION_ERROR"}
    except FileNotFoundError as exc:
        return 404, {"error": str(exc), "error_type": "NOT_FOUND"}


def api_save_program_data(body: dict):
    try:
        name = body.get("name", "")
        code = body.get("code", "")
        res = save_custom_program(name, code)
        return 200, res
    except ValueError as exc:
        return 400, {"success": False, "error": str(exc), "error_type": "VALIDATION_ERROR"}
    except Exception as exc:
        return 500, {"success": False, "error": f"Failed to save program: {exc}"}


def api_compile_program_data(body: dict):
    try:
        name = body.get("name", "")
        code = body.get("code", None)
        res = compile_program(name, code)
        return 200, res
    except ValueError as exc:
        return 400, {"success": False, "error": str(exc), "error_type": "VALIDATION_ERROR"}
    except FileNotFoundError as exc:
        return 404, {"success": False, "error": str(exc), "error_type": "NOT_FOUND"}
    except Exception as exc:
        return 500, {"success": False, "error": f"Compiler service error: {exc}"}


def api_delete_program_data(name: str):
    try:
        res = delete_custom_program(name)
        return 200, res
    except ValueError as exc:
        return 400, {"success": False, "error": str(exc), "error_type": "VALIDATION_ERROR"}
    except FileNotFoundError as exc:
        return 404, {"success": False, "error": str(exc), "error_type": "NOT_FOUND"}


def api_run_direct_data(body: dict):
    try:
        name = body.get("program") or body.get("name") or ""
        timeout_sec = float(body.get("timeout_sec", 15.0))
        timeout_sec = max(1.0, min(60.0, timeout_sec))
        async_mode = bool(body.get("async", False))
        res = start_debugger_session(
            program_name=name,
            use_trace=False,
            use_monitor=True,
            capture_output=True,
            mode="Direct Run",
            timeout_sec=timeout_sec,
            async_mode=async_mode
        )
        code = 200 if res.get("success", True) else 400
        return code, res
    except ValueError as exc:
        return 400, {"success": False, "error": str(exc), "error_type": "VALIDATION_ERROR"}
    except Exception as exc:
        return 500, {"success": False, "error": f"Execution failed: {exc}"}


def api_debug_data(body: dict):
    try:
        name = body.get("program") or body.get("name") or ""
        use_trace = bool(body.get("use_trace", True))
        use_monitor = bool(body.get("use_monitor", True))
        capture_output = bool(body.get("capture_output", True))
        timeout_sec = float(body.get("timeout_sec", 15.0))
        timeout_sec = max(1.0, min(60.0, timeout_sec))
        async_mode = bool(body.get("async", False))
        res = start_debugger_session(
            program_name=name,
            use_trace=use_trace,
            use_monitor=use_monitor,
            capture_output=capture_output,
            mode="Debugger",
            timeout_sec=timeout_sec,
            async_mode=async_mode
        )
        code = 200 if res.get("success", True) else 400
        return code, res
    except ValueError as exc:
        return 400, {"success": False, "error": str(exc), "error_type": "VALIDATION_ERROR"}
    except Exception as exc:
        return 500, {"success": False, "error": f"Debugger execution error: {exc}"}


def api_interactive_start_data(body: dict):
    try:
        name = body.get("program") or body.get("name") or "math_step"
        bps = body.get("breakpoints", [])
        res = create_interactive_session(name, bps)
        code = 200 if res.get("success") else 400
        return code, res
    except Exception as exc:
        return 500, {"success": False, "error": f"Interactive debugger start failed: {exc}"}


def api_interactive_action_data(body: dict, action: str):
    try:
        sid = body.get("session_id", "")
        if not sid:
            return 400, {"success": False, "error": "Missing session_id in request body."}
        res = execute_debugger_action(sid, action, body)
        code = 200 if res.get("success") else 400
        return code, res
    except Exception as exc:
        return 500, {"success": False, "error": f"Debugger action '{action}' failed: {exc}"}


def api_interactive_session_data(session_id: str):
    session = get_interactive_session(session_id)
    if not session:
        return 404, {"success": False, "error": f"Interactive session '{session_id}' not found."}
    return 200, {"success": True, "session": session.get_snapshot()}


def api_autodebug_data(body: dict):
    try:
        name = body.get("program") or body.get("name") or ""
        enable_gdb = bool(body.get("enable_gdb", True))
        timeout_sec = float(body.get("timeout_sec", 20.0))
        timeout_sec = max(1.0, min(60.0, timeout_sec))
        async_mode = bool(body.get("async", False))
        res = start_autodebug_session(
            program_name=name,
            enable_gdb=enable_gdb,
            timeout_sec=timeout_sec,
            async_mode=async_mode
        )
        code = 200 if res.get("success", True) else 400
        return code, res
    except ValueError as exc:
        return 400, {"success": False, "error": str(exc), "error_type": "VALIDATION_ERROR"}
    except Exception as exc:
        return 500, {"success": False, "error": f"AutoDebugger execution error: {exc}"}


def api_session_status_data(session_id: str):
    st = get_session_status(session_id)
    if st:
        return 200, st
    # Fall back to persisted reports if session completed earlier
    try:
        rep = get_report(session_id)
        return 200, rep
    except Exception:
        return 404, {"error": f"Session '{session_id}' not found.", "error_type": "NOT_FOUND"}


def api_session_stop_data(session_id: str):
    try:
        res = stop_session(session_id)
        return 200, res
    except FileNotFoundError as exc:
        return 404, {"success": False, "error": str(exc)}
    except Exception as exc:
        return 500, {"success": False, "error": str(exc)}


def api_monitor_data():
    active = get_active_sessions_summary()
    return 200, get_system_proc_overview(active)


def api_reports_list_data(query_params: dict):
    q = query_params.get("q", "")
    atype = query_params.get("type", "")
    rfilt = query_params.get("result", "")
    return 200, {"reports": list_reports(q, atype, rfilt)}


def api_report_get_data(session_id: str):
    try:
        return 200, get_report(session_id)
    except ValueError as exc:
        return 400, {"error": str(exc), "error_type": "CORRUPT_OR_INVALID_REPORT"}
    except FileNotFoundError as exc:
        return 404, {"error": str(exc), "error_type": "NOT_FOUND"}


def api_report_delete_data(session_id: str):
    try:
        return 200, delete_report(session_id)
    except ValueError as exc:
        return 400, {"success": False, "error": str(exc)}
    except FileNotFoundError as exc:
        return 404, {"success": False, "error": str(exc)}


# =====================================================================
# Flask Application Setup (if Flask is installed)
# =====================================================================

USING_FLASK = False
app = None

try:
    from flask import Flask, jsonify, request, Response, send_from_directory

    app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
    USING_FLASK = True

    @app.route("/")
    def route_landing():
        return Response(_read_template("landing.html"), mimetype="text/html")

    @app.route("/app")
    @app.route("/dashboard")
    def route_dashboard():
        return Response(_read_template("dashboard.html"), mimetype="text/html")

    @app.route("/api/health", methods=["GET"])
    def route_health():
        code, data = api_health_data()
        return jsonify(data), code

    @app.route("/api/dashboard", methods=["GET"])
    def route_api_dashboard():
        code, data = api_dashboard_data()
        return jsonify(data), code

    @app.route("/api/programs", methods=["GET", "POST"])
    def route_programs():
        if request.method == "GET":
            code, data = api_list_programs_data()
            return jsonify(data), code
        body = request.get_json(silent=True) or {}
        code, data = api_save_program_data(body)
        return jsonify(data), code

    @app.route("/api/programs/<path:name>", methods=["GET", "DELETE"])
    def route_program_item(name):
        if request.method == "GET":
            code, data = api_get_program_data(name)
            return jsonify(data), code
        code, data = api_delete_program_data(name)
        return jsonify(data), code

    @app.route("/api/compile", methods=["POST"])
    def route_compile():
        body = request.get_json(silent=True) or {}
        code, data = api_compile_program_data(body)
        return jsonify(data), code

    @app.route("/api/run", methods=["POST"])
    def route_run():
        body = request.get_json(silent=True) or {}
        code, data = api_run_direct_data(body)
        return jsonify(data), code

    @app.route("/api/debug", methods=["POST"])
    def route_debug():
        body = request.get_json(silent=True) or {}
        code, data = api_debug_data(body)
        return jsonify(data), code

    # Interactive GDB Source-Level Debugger Routes
    @app.route("/api/debugger/start", methods=["POST"])
    def route_debugger_start():
        body = request.get_json(silent=True) or {}
        code, data = api_interactive_start_data(body)
        return jsonify(data), code

    @app.route("/api/debugger/next", methods=["POST"])
    def route_debugger_next():
        body = request.get_json(silent=True) or {}
        code, data = api_interactive_action_data(body, "next")
        return jsonify(data), code

    @app.route("/api/debugger/step-into", methods=["POST"])
    def route_debugger_step_into():
        body = request.get_json(silent=True) or {}
        code, data = api_interactive_action_data(body, "step_into")
        return jsonify(data), code

    @app.route("/api/debugger/step-out", methods=["POST"])
    def route_debugger_step_out():
        body = request.get_json(silent=True) or {}
        code, data = api_interactive_action_data(body, "step_out")
        return jsonify(data), code

    @app.route("/api/debugger/continue", methods=["POST"])
    def route_debugger_continue():
        body = request.get_json(silent=True) or {}
        code, data = api_interactive_action_data(body, "continue")
        return jsonify(data), code

    @app.route("/api/debugger/breakpoint", methods=["POST"])
    def route_debugger_breakpoint():
        body = request.get_json(silent=True) or {}
        act = "remove_breakpoint" if body.get("action") == "remove" else "add_breakpoint"
        code, data = api_interactive_action_data(body, act)
        return jsonify(data), code

    @app.route("/api/debugger/select-frame", methods=["POST"])
    def route_debugger_select_frame():
        body = request.get_json(silent=True) or {}
        code, data = api_interactive_action_data(body, "select_frame")
        return jsonify(data), code

    @app.route("/api/debugger/stop", methods=["POST"])
    def route_debugger_stop():
        body = request.get_json(silent=True) or {}
        code, data = api_interactive_action_data(body, "stop")
        return jsonify(data), code

    @app.route("/api/debugger/save-report", methods=["POST"])
    def route_debugger_save_report():
        body = request.get_json(silent=True) or {}
        code, data = api_interactive_action_data(body, "save_report")
        return jsonify(data), code

    @app.route("/api/debugger/session/<session_id>", methods=["GET"])
    def route_debugger_session(session_id):
        code, data = api_interactive_session_data(session_id)
        return jsonify(data), code

    @app.route("/api/autodebug", methods=["POST"])
    def route_autodebug():
        body = request.get_json(silent=True) or {}
        code, data = api_autodebug_data(body)
        return jsonify(data), code

    @app.route("/api/session/<session_id>", methods=["GET"])
    def route_session_status(session_id):
        code, data = api_session_status_data(session_id)
        return jsonify(data), code

    @app.route("/api/session/<session_id>/stop", methods=["POST"])
    def route_session_stop(session_id):
        code, data = api_session_stop_data(session_id)
        return jsonify(data), code

    @app.route("/api/monitor", methods=["GET"])
    def route_monitor():
        code, data = api_monitor_data()
        return jsonify(data), code

    @app.route("/api/reports", methods=["GET"])
    def route_reports():
        params = {
            "q": request.args.get("q", ""),
            "type": request.args.get("type", ""),
            "result": request.args.get("result", "")
        }
        code, data = api_reports_list_data(params)
        return jsonify(data), code

    @app.route("/api/reports/<session_id>", methods=["GET", "DELETE"])
    def route_report_item(session_id):
        if request.method == "GET":
            code, data = api_report_get_data(session_id)
            return jsonify(data), code
        code, data = api_report_delete_data(session_id)
        return jsonify(data), code

    @app.route("/api/reports/<session_id>/export/<fmt>", methods=["GET"])
    def route_report_export(session_id, fmt):
        try:
            if fmt.lower() == "txt":
                txt = get_report_txt(session_id)
                return Response(
                    txt,
                    mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{session_id}.txt"'}
                )
            elif fmt.lower() == "json":
                rep = get_report(session_id)
                return Response(
                    json.dumps(rep, indent=2),
                    mimetype="application/json; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{session_id}.json"'}
                )
            return jsonify({"error": "Unsupported export format. Use txt or json."}), 400
        except FileNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

except ImportError:
    USING_FLASK = False


# =====================================================================
# Standard-Library HTTP Fallback Handler (when Flask is not installed)
# =====================================================================

class LDSTFallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Quiet standard access logs unless LDST_VERBOSE=1
        if os.environ.get("LDST_VERBOSE") == "1":
            super().log_message(fmt, *args)

    def _send_json(self, status_code: int, payload: dict):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, status_code: int, html_text: str):
        raw = html_text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8", errors="replace"))
        except Exception:
            return {}

    def _serve_static(self, rel_path: str):
        safe_rel = os.path.normpath(rel_path).lstrip("/\\")
        full_path = os.path.realpath(os.path.join(STATIC_DIR, safe_rel))
        static_real = os.path.realpath(STATIC_DIR)
        if not full_path.startswith(static_real + os.sep) or not os.path.isfile(full_path):
            self._send_json(404, {"error": "Static asset not found."})
            return
        ctype, _ = mimetypes.guess_type(full_path)
        ctype = ctype or "application/octet-stream"
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

            if path == "/":
                return self._send_html(200, _read_template("landing.html"))
            if path in ("/app", "/dashboard"):
                return self._send_html(200, _read_template("dashboard.html"))
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/api/health":
                return self._send_json(*api_health_data())
            if path == "/api/dashboard":
                return self._send_json(*api_dashboard_data())
            if path == "/api/programs":
                return self._send_json(*api_list_programs_data())
            if path.startswith("/api/programs/"):
                prog_name = path[len("/api/programs/"):]
                return self._send_json(*api_get_program_data(prog_name))
            if path.startswith("/api/session/"):
                sid = path[len("/api/session/"):]
                return self._send_json(*api_session_status_data(sid))
            if path.startswith("/api/debugger/session/"):
                sid = path[len("/api/debugger/session/"):]
                return self._send_json(*api_interactive_session_data(sid))
            if path == "/api/monitor":
                return self._send_json(*api_monitor_data())
            if path == "/api/reports":
                return self._send_json(*api_reports_list_data(qs))
            if path.startswith("/api/reports/"):
                rest = path[len("/api/reports/"):]
                if "/export/" in rest:
                    sid, fmt = rest.split("/export/", 1)
                    try:
                        if fmt.lower() == "txt":
                            raw = get_report_txt(sid).encode("utf-8")
                            self.send_response(200)
                            self.send_header("Content-Type", "text/plain; charset=utf-8")
                            self.send_header("Content-Disposition", f'attachment; filename="{sid}.txt"')
                            self.send_header("Content-Length", str(len(raw)))
                            self.end_headers()
                            self.wfile.write(raw)
                            return
                        elif fmt.lower() == "json":
                            rep = get_report(sid)
                            raw = json.dumps(rep, indent=2).encode("utf-8")
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json; charset=utf-8")
                            self.send_header("Content-Disposition", f'attachment; filename="{sid}.json"')
                            self.send_header("Content-Length", str(len(raw)))
                            self.end_headers()
                            self.wfile.write(raw)
                            return
                        return self._send_json(400, {"error": "Unsupported export format."})
                    except FileNotFoundError as exc:
                        return self._send_json(404, {"error": str(exc)})
                    except ValueError as exc:
                        return self._send_json(400, {"error": str(exc)})
                return self._send_json(*api_report_get_data(rest))

            self._send_json(404, {"error": f"Endpoint '{path}' not found."})
        except Exception as exc:
            traceback.print_exc()
            self._send_json(500, {"error": f"Internal backend error: {exc}"})

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            body = self._read_json_body()

            if path == "/api/programs":
                return self._send_json(*api_save_program_data(body))
            if path == "/api/compile":
                return self._send_json(*api_compile_program_data(body))
            if path == "/api/run":
                return self._send_json(*api_run_direct_data(body))
            if path == "/api/debug":
                return self._send_json(*api_debug_data(body))
            if path == "/api/debugger/start":
                return self._send_json(*api_interactive_start_data(body))
            if path == "/api/debugger/next":
                return self._send_json(*api_interactive_action_data(body, "next"))
            if path == "/api/debugger/step-into":
                return self._send_json(*api_interactive_action_data(body, "step_into"))
            if path == "/api/debugger/step-out":
                return self._send_json(*api_interactive_action_data(body, "step_out"))
            if path == "/api/debugger/continue":
                return self._send_json(*api_interactive_action_data(body, "continue"))
            if path == "/api/debugger/breakpoint":
                act = "remove_breakpoint" if body.get("action") == "remove" else "add_breakpoint"
                return self._send_json(*api_interactive_action_data(body, act))
            if path == "/api/debugger/select-frame":
                return self._send_json(*api_interactive_action_data(body, "select_frame"))
            if path == "/api/debugger/stop":
                return self._send_json(*api_interactive_action_data(body, "stop"))
            if path == "/api/debugger/save-report":
                return self._send_json(*api_interactive_action_data(body, "save_report"))
            if path == "/api/autodebug":
                return self._send_json(*api_autodebug_data(body))
            if path.startswith("/api/session/") and path.endswith("/stop"):
                sid = path[len("/api/session/"):-len("/stop")]
                return self._send_json(*api_session_stop_data(sid))

            self._send_json(404, {"error": f"POST endpoint '{path}' not found."})
        except Exception as exc:
            traceback.print_exc()
            self._send_json(500, {"error": f"Internal backend error: {exc}"})

    def do_DELETE(self):
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)

            if path.startswith("/api/programs/"):
                prog_name = path[len("/api/programs/"):]
                return self._send_json(*api_delete_program_data(prog_name))
            if path.startswith("/api/reports/"):
                sid = path[len("/api/reports/"):]
                return self._send_json(*api_report_delete_data(sid))

            self._send_json(404, {"error": f"DELETE endpoint '{path}' not found."})
        except Exception as exc:
            traceback.print_exc()
            self._send_json(500, {"error": f"Internal backend error: {exc}"})


def main():
    ensure_directories()
    ensure_core_built()

    host = os.environ.get("LDST_HOST", "127.0.0.1")
    port = int(os.environ.get("LDST_PORT", "5000"))

    # Check if port is already in use before starting
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((host, port)) == 0:
            print(f"\n[ERROR] Port {port} on {host} is already in use.", file=sys.stderr)
            print(f"Stop the existing process using port {port} or set LDST_PORT=<port>.\n", file=sys.stderr)
            sys.exit(1)

    if USING_FLASK and app is not None:
        app.run(host=host, port=port, debug=False, threaded=True)
    else:
        ThreadingHTTPServer.allow_reuse_address = True
        server = ThreadingHTTPServer((host, port), LDSTFallbackHandler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
