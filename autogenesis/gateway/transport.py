"""stdio and WebSocket adapters for :mod:`autogenesis.gateway.service`."""

from __future__ import annotations

import asyncio
import hmac
import json
import sys
from contextlib import suppress
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from autogenesis.gateway.protocol import GatewayCommand, error_response
from autogenesis.gateway.service import AgentGateway


def _encode(message) -> str:
    return message.model_dump_json()


async def serve_stdio(gateway: AgentGateway) -> None:
    """Serve JSON Lines over standard streams without mixing in runtime logs."""
    event_queue = await gateway.subscribe()

    async def write_events() -> None:
        while True:
            message = await event_queue.get()
            print(_encode(message), flush=True)

    writer = asyncio.create_task(write_events(), name="gateway-stdio-events")
    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            try:
                raw = json.loads(line)
                command = GatewayCommand.model_validate(raw)
                response = await gateway.handle(command)
            except json.JSONDecodeError as exc:
                response = error_response("unknown", "invalid_json", str(exc))
            except ValidationError as exc:
                response = error_response("unknown", "invalid_command", str(exc))
            print(_encode(response), flush=True)
    finally:
        writer.cancel()
        with suppress(asyncio.CancelledError):
            await writer
        gateway.unsubscribe(event_queue)


def create_websocket_app(
    gateway: AgentGateway, *, token: Optional[str] = None,
    allowed_origins: Optional[set[str]] = None,
):
    """Create the optional FastAPI transport without importing it for stdio mode."""
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Autogenesis Gateway", version="1.0.0")

    @app.get("/health")
    async def health():
        return JSONResponse({"ok": True, "protocol_version": 1})

    @app.get("/ide/resolve/{session_id}")
    async def ide_resolve(session_id: str, port: int = 0):
        """Tell the UI's IDE proxy where a session's container port lives.

        ``/ide/<session>/`` on the UI's origin reaches the editor itself; the
        host form ``<port>-<session>.ide.localhost`` reaches any other port in
        that container, so a dev server or an OAuth callback listener started in
        the integrated terminal is reachable with no per-tool support. The Vite
        dev server matches either and asks here for the upstream to forward to.

        Bound to loopback like the rest of the gateway, and it returns nothing
        for an unknown session, so it cannot be used to probe other sessions.
        """
        from autogenesis.ide import ide_manager

        upstream = (
            await ide_manager.upstream_for_port(session_id, port) if port
            else ide_manager.upstream(session_id)
        )
        if not upstream:
            return JSONResponse({"ok": False, "error": "no IDE for this session"}, status_code=404)
        return JSONResponse({"ok": True, "upstream": upstream})

    @app.get("/science/resolve/{session_id}")
    async def science_resolve(session_id: str):
        """Tell the UI's proxy where a project's JupyterLab lives.

        A Jupyter Server in this container, on a loopback port of its own —
        the same server the agent's kernel runs in, which is what makes the Lab
        and the agent share variables. Unlike the IDE route this takes no
        ``port``: anything a notebook starts is reached through
        jupyter-server-proxy on that same one.
        """
        from autogenesis.science import science_manager

        upstream = science_manager.upstream(session_id)
        if not upstream:
            return JSONResponse({"ok": False, "error": "no workstation for this project"}, status_code=404)
        return JSONResponse({"ok": True, "upstream": upstream})

    def _authorize(websocket: WebSocket) -> bool:
        supplied_token = websocket.query_params.get("token") or websocket.headers.get("authorization", "").removeprefix("Bearer ")
        supplied_token = supplied_token or ""
        if token and not hmac.compare_digest(supplied_token, token):
            return False
        origin = websocket.headers.get("origin")
        if allowed_origins is not None and origin not in allowed_origins:
            return False
        return True

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        if not _authorize(websocket):
            await websocket.close(code=1008, reason="Unauthorized")
            return
        await websocket.accept()
        event_queue = await gateway.subscribe()
        outbound: asyncio.Queue[str] = asyncio.Queue(maxsize=2_000)

        async def forward_events() -> None:
            while True:
                await outbound.put(_encode(await event_queue.get()))

        async def write_messages() -> None:
            while True:
                await websocket.send_text(await outbound.get())

        forwarder = asyncio.create_task(forward_events(), name="gateway-websocket-events")
        writer = asyncio.create_task(write_messages(), name="gateway-websocket-writer")
        try:
            while True:
                try:
                    command = GatewayCommand.model_validate_json(await websocket.receive_text())
                    response = await gateway.handle(command)
                except ValidationError as exc:
                    response = error_response("unknown", "invalid_command", str(exc))
                await outbound.put(_encode(response))
        except WebSocketDisconnect:
            pass
        finally:
            forwarder.cancel()
            writer.cancel()
            await asyncio.gather(forwarder, writer, return_exceptions=True)
            gateway.unsubscribe(event_queue)

    @app.websocket("/env/vnc")
    async def vnc_relay(websocket: WebSocket):
        """Relay the browser's noVNC connection to the sandbox websockify endpoint.

        The browser environment's websockify is reachable only via an ephemeral
        host port (assigned by the opensandbox proxy). Rather than exposing that
        port, the client connects here on the fixed gateway origin and we pipe
        frames to/from the upstream target cached by the gateway. This keeps the
        remote experience to a single forwarded port (the UI).
        """
        if not _authorize(websocket):
            await websocket.close(code=1008, reason="Unauthorized")
            return
        target = gateway._latest_vnc_target
        # noVNC negotiates a subprotocol ("binary"/"base64"); echo the client's
        # choice on accept and to the upstream, or the RFB handshake fails.
        requested = websocket.headers.get("sec-websocket-protocol", "")
        protocols = [p.strip() for p in requested.split(",") if p.strip()]
        subprotocol = protocols[0] if protocols else None
        await websocket.accept(subprotocol=subprotocol)
        if not target:
            await websocket.close(code=1011, reason="No live VNC target")
            return

        import aiohttp

        async with aiohttp.ClientSession() as session:
            try:
                upstream = await session.ws_connect(
                    target, protocols=protocols or (), autoping=True
                )
            except Exception:
                with suppress(Exception):
                    await websocket.close(code=1011, reason="VNC upstream unreachable")
                return

            async def client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        return
                    if (data := message.get("bytes")) is not None:
                        await upstream.send_bytes(data)
                    elif (text := message.get("text")) is not None:
                        await upstream.send_str(text)

            async def upstream_to_client() -> None:
                async for msg in upstream:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        await websocket.send_bytes(msg.data)
                    elif msg.type == aiohttp.WSMsgType.TEXT:
                        await websocket.send_text(msg.data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                        return

            c2u = asyncio.create_task(client_to_upstream(), name="vnc-c2u")
            u2c = asyncio.create_task(upstream_to_client(), name="vnc-u2c")
            try:
                await asyncio.wait({c2u, u2c}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                c2u.cancel()
                u2c.cancel()
                await asyncio.gather(c2u, u2c, return_exceptions=True)
                with suppress(Exception):
                    await upstream.close()
                with suppress(Exception):
                    await websocket.close()

    return app
