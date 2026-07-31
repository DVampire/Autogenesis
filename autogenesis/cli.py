"""The single console entry point for Autogenesis.

The ``autogenesis`` command owns all user-facing modes: a one-shot control
command, the interactive terminal loop (``tui``), and the Gateway service
(``serve``). Three small objects, one job each:

- :class:`GatewayLauncher` runs the AgentGateway over a transport (``serve``).
- :class:`TerminalClient` drives an in-process Gateway for control commands and
  the tui — the terminal is a *client* of the single backend, not a second one.
- :class:`Console` parses argv and routes the mode.

The Gateway is the single backend: it owns every capability manager's lifecycle.
The one-shot command and the tui do NOT bootstrap managers themselves — they go
through the Gateway (``session.create`` + ``command.execute``), so there is
exactly one place that initializes capabilities and one command-dispatch path.

Examples:
    autogenesis /help
    autogenesis /registry
    autogenesis /checkpoint pre-evolve
    autogenesis --config configs/meta_agent.py /registry
"""
import argparse
import asyncio
import ipaddress
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from autogenesis.port import GATEWAY as GATEWAY_PORT


class TerminalClient:
    """Runs control commands / the tui against an in-process Gateway.

    The Gateway owns every capability manager, so the terminal is just a client:
    it opens a Gateway, creates a session, and dispatches ``command.execute`` —
    no parallel bootstrap.
    """

    def __init__(self, config_path: str) -> None:
        self._config_path = config_path

    @asynccontextmanager
    async def _session(self):
        """Open an in-process Gateway + session; stop the Gateway on exit."""
        from autogenesis.gateway.protocol import GatewayCommand
        from autogenesis.gateway.service import AgentGateway
        from autogenesis.utils import make_id

        gateway = AgentGateway(workspace_source=Path.cwd())
        await gateway.start(self._config_path, stdio=True)
        try:
            created = await gateway.handle(GatewayCommand(id=make_id(), method="session.create"))
            if not created.ok:
                raise RuntimeError(created.error.message if created.error else "session.create failed")
            yield gateway, created.result["session_id"]
        finally:
            await gateway.stop()

    @staticmethod
    async def _dispatch(gateway, session_id: str, raw: str) -> Tuple[bool, str]:
        """Run one slash command through the Gateway's ``command.execute``."""
        from autogenesis.gateway.protocol import GatewayCommand
        from autogenesis.utils import make_id

        resp = await gateway.handle(GatewayCommand(
            id=make_id(), method="command.execute",
            params={"session_id": session_id, "raw": raw},
        ))
        if not resp.ok:
            return False, resp.error.message if resp.error else "command failed"
        return bool(resp.result.get("success")), str(resp.result.get("message", ""))

    async def run_command(self, raw: str) -> int:
        """Run a single control command and print its result."""
        async with self._session() as (gateway, session_id):
            ok, message = await self._dispatch(gateway, session_id, raw)
        print(("✅ " if ok else "❌ ") + raw)
        print(message)
        return 0 if ok else 1

    async def run_tui(self) -> int:
        """Run the interactive terminal loop over one Gateway session."""
        print("Autogenesis terminal mode. Type /help for commands; /exit to quit.")
        async with self._session() as (gateway, session_id):
            while True:
                try:
                    raw = input("autogenesis> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return 0
                if not raw:
                    continue
                if raw.lstrip("/").lower() in {"exit", "quit"}:
                    return 0
                ok, message = await self._dispatch(gateway, session_id, raw)
                print(("✅ " if ok else "❌ ") + message)


class GatewayLauncher:
    """Runs the AgentGateway over a transport (the ``serve`` mode)."""

    def __init__(self, config_path: str, transport: str = "stdio", host: str = "127.0.0.1",
                 port: int = GATEWAY_PORT, token: Optional[str] = None,
                 allow_origins: Optional[Sequence[str]] = None) -> None:
        self._config_path = config_path
        self._transport = transport
        self._host = host
        self._port = port
        self._token = token
        self._allow_origins = allow_origins

    @classmethod
    def from_args(cls, argv: Optional[Sequence[str]]) -> "GatewayLauncher":
        parser = argparse.ArgumentParser(prog="autogenesis serve", description="Run the Autogenesis Gateway")
        parser.add_argument("--config", default="configs/meta_agent.py")
        parser.add_argument("--transport", choices=("stdio", "websocket"), default="stdio")
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=GATEWAY_PORT)
        parser.add_argument("--token", default=os.getenv("AUTOGENESIS_GATEWAY_TOKEN"))
        parser.add_argument("--allow-origin", action="append", default=None,
                            help="Allowed WebSocket Origin; repeat for multiple browser origins")
        args = parser.parse_args(argv)
        if args.transport == "websocket":
            is_loopback = args.host == "localhost"
            try:
                is_loopback = ipaddress.ip_address(args.host).is_loopback
            except ValueError:
                pass
            if not is_loopback and not args.token:
                parser.error("--token (or AUTOGENESIS_GATEWAY_TOKEN) is required for non-loopback hosts")
        return cls(args.config, args.transport, args.host, args.port, args.token, args.allow_origin)

    def run(self) -> int:
        if self._transport == "stdio":
            return asyncio.run(self._serve_stdio())
        return self._serve_websocket()

    async def _serve_stdio(self) -> int:
        from autogenesis.gateway.service import AgentGateway
        from autogenesis.gateway.transport import serve_stdio

        gateway = AgentGateway(workspace_source=Path.cwd())
        await gateway.start(self._config_path, stdio=True)
        try:
            await serve_stdio(gateway)
        finally:
            await gateway.stop()
        return 0

    def _serve_websocket(self) -> int:
        import uvicorn

        from autogenesis.gateway.service import AgentGateway
        from autogenesis.gateway.transport import create_websocket_app
        from autogenesis.port import port_manager

        gateway = AgentGateway(workspace_source=Path.cwd())

        @asynccontextmanager
        async def lifespan(app):
            await gateway.start(self._config_path)
            try:
                yield
            finally:
                await gateway.stop()

        app = create_websocket_app(
            gateway, token=self._token,
            allowed_origins=set(self._allow_origins) if self._allow_origins else None,
        )
        app.router.lifespan_context = lifespan
        port_manager.register("gateway", self._port, type="host")
        uvicorn.run(app, host=self._host, port=self._port, log_level="info")
        return 0


class Console:
    """The ``autogenesis`` entry: routes serve / tui / <command> to the Gateway."""

    def __init__(self, argv: Sequence[str]) -> None:
        self._argv = list(argv)

    def run(self) -> int:
        mode, remainder = self._mode_and_remainder()
        if mode == "serve":
            return GatewayLauncher.from_args(remainder).run()
        if mode == "tui":
            return self._run_tui(remainder)
        return self._run_command(self._argv)

    def _mode_and_remainder(self) -> Tuple[Optional[str], List[str]]:
        """Find the first positional mode while accepting ``--config`` before it."""
        values = list(self._argv)
        index = 0
        while index < len(values):
            value = values[index]
            if value == "--config":
                index += 2
                continue
            if value.startswith("--config="):
                index += 1
                continue
            if not value.startswith("-"):
                return value, [*values[:index], *values[index + 1:]]
            index += 1
        return None, values

    @staticmethod
    def _run_tui(argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="autogenesis tui", description="Run the interactive terminal interface")
        parser.add_argument("--config", default="configs/meta_agent.py", help="config file for registered capabilities")
        args = parser.parse_args(argv)
        return asyncio.run(TerminalClient(args.config).run_tui())

    @staticmethod
    def _run_command(argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="autogenesis", description="Autogenesis control commands")
        parser.add_argument("command", nargs=argparse.REMAINDER, help="the command line, e.g. /registry")
        parser.add_argument("--config", help="config file (determines which capabilities are registered).")
        args = parser.parse_args(argv)
        if not args.command:
            print("usage: autogenesis /<command> [args]   (try: autogenesis /help)")
            return 0
        return asyncio.run(TerminalClient(args.config or "configs/base.py").run_command(" ".join(args.command)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Console entry point (pyproject: ``autogenesis = autogenesis.cli:main``)."""
    return Console(sys.argv[1:] if argv is None else argv).run()


def gateway_main(argv: Optional[Sequence[str]] = None) -> int:
    """Start the Gateway directly — used by ``python -m autogenesis.gateway`` and tests."""
    return GatewayLauncher.from_args(argv).run()


if __name__ == "__main__":
    raise SystemExit(main())
