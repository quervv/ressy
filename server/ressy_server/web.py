from __future__ import annotations

import asyncio
import json
import logging

from aiohttp import WSMsgType, web

from . import __version__
from .hub import AgentConnection, Hub
from .protocol import MAX_WS_MESSAGE, clean_name

log = logging.getLogger("ressy.web")

HUB_KEY = web.AppKey("hub", Hub)
HELLO_TIMEOUT_S = 15.0
HEARTBEAT_S = 25.0


def _client_ip(request: web.Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.remote or "?"


async def _send_error(ws: web.WebSocketResponse, code: str, message: str) -> None:
    try:
        await ws.send_str(json.dumps({"type": "error", "code": code, "message": message}))
    except Exception:
        pass


async def agent_socket(request: web.Request) -> web.StreamResponse:
    hub = request.app[HUB_KEY]
    ws = web.WebSocketResponse(heartbeat=HEARTBEAT_S, max_msg_size=MAX_WS_MESSAGE)
    await ws.prepare(request)
    ip = _client_ip(request, hub.settings.trust_proxy)

    try:
        first = await ws.receive(timeout=HELLO_TIMEOUT_S)
    except asyncio.TimeoutError:
        await ws.close(code=4000, message=b"hello timeout")
        return ws
    if first.type != WSMsgType.TEXT:
        await ws.close(code=4002, message=b"expected hello")
        return ws
    try:
        hello = json.loads(first.data)
    except (TypeError, ValueError):
        hello = None
    if not isinstance(hello, dict) or hello.get("type") != "hello":
        await _send_error(ws, "bad_hello", "Il primo messaggio deve essere 'hello'.")
        await ws.close(code=4002, message=b"expected hello")
        return ws

    record, error = await hub.authenticate(hello, ip)
    if record is None:
        messages = {
            "auth_failed": "Identità del PC non valida. Rigenera l'identità dalle impostazioni di Ressy.",
            "rate_limited": "Troppe registrazioni da questo indirizzo, riprova più tardi.",
            "unsupported_protocol": "Versione di Ressy non compatibile con il server: aggiorna l'app.",
            "bad_hello": "Messaggio di autenticazione non valido.",
        }
        await _send_error(ws, error or "auth_failed", messages.get(error or "", "Accesso negato."))
        await ws.close(code=4003, message=(error or "denied").encode())
        return ws

    conn = AgentConnection(
        agent_id=record.agent_id,
        name=clean_name(hello.get("name"), fallback=record.name or "PC"),
        version=clean_name(hello.get("version"), fallback="?")[:32],
        ws=ws,
        remote=ip,
    )
    graceful = False
    try:
        await hub.agent_connected(conn)
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    log.debug("invalid JSON from %s", conn.agent_id[:8])
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("type") == "bye":
                    graceful = True
                    break
                try:
                    await hub.handle_agent_message(conn, data)
                except Exception:
                    log.exception("error handling %r from %s", data.get("type"), conn.agent_id[:8])
            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                break
    finally:
        await asyncio.shield(hub.agent_disconnected(conn, graceful=graceful))
        if not ws.closed:
            await ws.close()
    return ws


async def health(request: web.Request) -> web.Response:
    hub = request.app[HUB_KEY]
    return web.json_response({"ok": True, "version": __version__, "agents_online": hub.online_count})


def create_app(hub: Hub) -> web.Application:
    app = web.Application()
    app[HUB_KEY] = hub
    app.router.add_get("/ws/agent", agent_socket)
    app.router.add_get("/health", health)
    return app
