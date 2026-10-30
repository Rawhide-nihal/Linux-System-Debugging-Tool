"""
Linux System Debugging Tool - SQLite Storage & Session History
Stores workspaces, debug sessions, test cases, and diagnostic reports.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import DB_PATH

_DB_LOCK = threading.Lock()


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _DB_LOCK:
        conn = get_db_connection()
        cur = conn.cursor()

        # Workspaces table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Debug sessions table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                executable TEXT NOT NULL,
                status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                exit_code INTEGER,
                signal_info TEXT,
                breakpoints_json TEXT,
                timeline_json TEXT,
                report_json TEXT,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
            )
        """)

        # Test cases table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS test_cases (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                stdin_data TEXT,
                expected_output TEXT,
                expected_exit_code INTEGER,
                last_run_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
            )
        """)

        # Reports table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                session_id TEXT,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()


# Initialize database upon import
init_db()


class StorageService:
    """Provides thread-safe access to persistent application state."""

    @staticmethod
    def save_workspace(ws_id: str, name: str, path: str, config: Dict[str, Any]):
        now = datetime.now(timezone.utc).isoformat()
        with _DB_LOCK:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO workspaces (id, name, path, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    path = excluded.path,
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
            """, (ws_id, name, path, json.dumps(config), now, now))
            conn.commit()
            conn.close()

    @staticmethod
    def list_workspaces() -> List[Dict[str, Any]]:
        with _DB_LOCK:
            conn = get_db_connection()
            rows = conn.execute("SELECT * FROM workspaces ORDER BY updated_at DESC").fetchall()
            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "name": r["name"],
                    "path": r["path"],
                    "config": json.loads(r["config_json"]),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"]
                })
            conn.close()
            return result

    @staticmethod
    def get_workspace(ws_id: str) -> Optional[Dict[str, Any]]:
        with _DB_LOCK:
            conn = get_db_connection()
            row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
            conn.close()
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "path": row["path"],
                "config": json.loads(row["config_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }

    @staticmethod
    def delete_workspace(ws_id: str):
        with _DB_LOCK:
            conn = get_db_connection()
            conn.execute("DELETE FROM workspaces WHERE id = ?", (ws_id,))
            conn.commit()
            conn.close()

    @staticmethod
    def save_session(session_id: str, ws_id: str, executable: str, status: str,
                     start_time: str, end_time: Optional[str] = None,
                     exit_code: Optional[int] = None, signal_info: Optional[str] = None,
                     breakpoints: Optional[List[Any]] = None, timeline: Optional[List[Any]] = None,
                     report: Optional[Dict[str, Any]] = None):
        with _DB_LOCK:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO sessions (id, workspace_id, executable, status, start_time, end_time,
                                     exit_code, signal_info, breakpoints_json, timeline_json, report_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    end_time = excluded.end_time,
                    exit_code = excluded.exit_code,
                    signal_info = excluded.signal_info,
                    breakpoints_json = excluded.breakpoints_json,
                    timeline_json = excluded.timeline_json,
                    report_json = excluded.report_json
            """, (
                session_id, ws_id, executable, status, start_time, end_time, exit_code, signal_info,
                json.dumps(breakpoints or []), json.dumps(timeline or []), json.dumps(report or {})
            ))
            conn.commit()
            conn.close()

    @staticmethod
    def list_sessions(ws_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with _DB_LOCK:
            conn = get_db_connection()
            if ws_id:
                rows = conn.execute("SELECT * FROM sessions WHERE workspace_id = ? ORDER BY start_time DESC", (ws_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM sessions ORDER BY start_time DESC").fetchall()
            res = []
            for r in rows:
                res.append({
                    "id": r["id"],
                    "workspace_id": r["workspace_id"],
                    "executable": r["executable"],
                    "status": r["status"],
                    "start_time": r["start_time"],
                    "end_time": r["end_time"],
                    "exit_code": r["exit_code"],
                    "signal_info": r["signal_info"],
                    "breakpoints": json.loads(r["breakpoints_json"] or "[]"),
                    "timeline": json.loads(r["timeline_json"] or "[]"),
                    "report": json.loads(r["report_json"] or "{}")
                })
            conn.close()
            return res

    @staticmethod
    def get_session(session_id: str) -> Optional[Dict[str, Any]]:
        with _DB_LOCK:
            conn = get_db_connection()
            r = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            conn.close()
            if not r:
                return None
            return {
                "id": r["id"],
                "workspace_id": r["workspace_id"],
                "executable": r["executable"],
                "status": r["status"],
                "start_time": r["start_time"],
                "end_time": r["end_time"],
                "exit_code": r["exit_code"],
                "signal_info": r["signal_info"],
                "breakpoints": json.loads(r["breakpoints_json"] or "[]"),
                "timeline": json.loads(r["timeline_json"] or "[]"),
                "report": json.loads(r["report_json"] or "{}")
            }

    @staticmethod
    def save_test_case(tc_id: str, ws_id: str, name: str, args: List[str], stdin_data: str,
                       expected_output: str, expected_exit_code: int):
        now = datetime.now(timezone.utc).isoformat()
        with _DB_LOCK:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO test_cases (id, workspace_id, name, args_json, stdin_data,
                                       expected_output, expected_exit_code, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    args_json = excluded.args_json,
                    stdin_data = excluded.stdin_data,
                    expected_output = excluded.expected_output,
                    expected_exit_code = excluded.expected_exit_code
            """, (tc_id, ws_id, name, json.dumps(args), stdin_data, expected_output, expected_exit_code, now))
            conn.commit()
            conn.close()

    @staticmethod
    def update_test_case_run(tc_id: str, last_run: Dict[str, Any]):
        with _DB_LOCK:
            conn = get_db_connection()
            conn.execute("UPDATE test_cases SET last_run_json = ? WHERE id = ?", (json.dumps(last_run), tc_id))
            conn.commit()
            conn.close()

    @staticmethod
    def list_test_cases(ws_id: str) -> List[Dict[str, Any]]:
        with _DB_LOCK:
            conn = get_db_connection()
            rows = conn.execute("SELECT * FROM test_cases WHERE workspace_id = ? ORDER BY created_at ASC", (ws_id,)).fetchall()
            res = []
            for r in rows:
                res.append({
                    "id": r["id"],
                    "workspace_id": r["workspace_id"],
                    "name": r["name"],
                    "args": json.loads(r["args_json"] or "[]"),
                    "stdin_data": r["stdin_data"] or "",
                    "expected_output": r["expected_output"] or "",
                    "expected_exit_code": r["expected_exit_code"] if r["expected_exit_code"] is not None else 0,
                    "last_run": json.loads(r["last_run_json"]) if r["last_run_json"] else None,
                    "created_at": r["created_at"]
                })
            conn.close()
            return res

    @staticmethod
    def delete_test_case(tc_id: str):
        with _DB_LOCK:
            conn = get_db_connection()
            conn.execute("DELETE FROM test_cases WHERE id = ?", (tc_id,))
            conn.commit()
            conn.close()

    @staticmethod
    def save_report(report_id: str, ws_id: str, session_id: Optional[str],
                    title: str, summary: str, findings: List[Dict[str, Any]]):
        now = datetime.now(timezone.utc).isoformat()
        with _DB_LOCK:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO reports (id, workspace_id, session_id, title, summary, findings_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (report_id, ws_id, session_id, title, summary, json.dumps(findings), now))
            conn.commit()
            conn.close()

    @staticmethod
    def list_reports(ws_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with _DB_LOCK:
            conn = get_db_connection()
            if ws_id:
                rows = conn.execute("SELECT * FROM reports WHERE workspace_id = ? ORDER BY created_at DESC", (ws_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
            res = []
            for r in rows:
                res.append({
                    "id": r["id"],
                    "workspace_id": r["workspace_id"],
                    "session_id": r["session_id"],
                    "title": r["title"],
                    "summary": r["summary"],
                    "findings": json.loads(r["findings_json"] or "[]"),
                    "created_at": r["created_at"]
                })
            conn.close()
            return res
