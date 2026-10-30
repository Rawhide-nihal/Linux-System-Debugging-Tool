"""
Linux System Debugging Tool - WebSocket Real-Time Event & Terminal Router
Streams asynchronous GDB events and bridges interactive terminal I/O over WebSockets.
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set

from ..debugger.session_manager import SessionManager

router = APIRouter(tags=["websockets"])

# Active WebSocket connections per session
_ACTIVE_CONNECTIONS: Dict[str, Set[WebSocket]] = {}


def broadcast_session_event(event: Dict[str, Any]):
    session_id = event.get("session_id")
    if not session_id or session_id not in _ACTIVE_CONNECTIONS:
        return

    msg_str = json.dumps(event)
    dead_sockets = set()
    for ws in list(_ACTIVE_CONNECTIONS[session_id]):
        try:
            asyncio.create_task(ws.send_text(msg_str))
        except Exception:
            dead_sockets.add(ws)

    for ws in dead_sockets:
        _ACTIVE_CONNECTIONS[session_id].discard(ws)


@router.websocket("/ws/debugger/{session_id}")
async def debugger_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if session_id not in _ACTIVE_CONNECTIONS:
        _ACTIVE_CONNECTIONS[session_id] = set()
    _ACTIVE_CONNECTIONS[session_id].add(websocket)

    sess = SessionManager.get_session(session_id)
    if sess:
        # Register the broadcast callback
        sess.event_callback = broadcast_session_event
        # Send initial snapshot
        await websocket.send_text(json.dumps({
            "event": "snapshot",
            "session_id": session_id,
            "data": sess.get_snapshot()
        }))

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                action = msg.get("action")
                current_sess = SessionManager.get_session(session_id)
                if not current_sess:
                    continue

                if action == "stdin":
                    text = msg.get("text", "")
                    current_sess.send_stdin(text)
                elif action == "step_over":
                    current_sess.step_over()
                elif action == "step_into":
                    current_sess.step_into()
                elif action == "step_out":
                    current_sess.step_out()
                elif action == "continue":
                    current_sess.continue_exec()
                elif action == "pause":
                    current_sess.pause()
            except Exception:
                pass
    except WebSocketDisconnect:
        if session_id in _ACTIVE_CONNECTIONS:
            _ACTIVE_CONNECTIONS[session_id].discard(websocket)
