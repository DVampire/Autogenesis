"""Connector Context Manager for loading, managing, and serving connectors (MCP servers)."""

import os
import sys
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from autogenesis.logger import logger
from autogenesis.paths import P, path_manager
from autogenesis.config import config
from autogenesis.connector.types import ConnectorConfig, ConnectorContext
from autogenesis.response.types import Response, ResponseType
from autogenesis.session import SessionContext
from autogenesis.utils import assemble_workspace_path, file_lock, render_capability_card
from autogenesis.version import version_manager
from autogenesis.permission import permission_manager, PermissionMode


class ConnectorContextManager(BaseModel):
    """Manages the lifecycle of connectors: discovery, loading, registration, update, and execution.

    A connector wraps a single MCP server: its connection config plus the actions
    (MCP tools) it exposes. Mirrors the SkillContextManager so the two subsystems
    behave identically; the only domain differences are that a connector is defined
    by a ``connector.json`` (instead of ``SKILL.md``) and executing one routes an
    ``action``/``args`` call to the MCP server (instead of returning instructions).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default=None, description="Base directory for connector runtime data")
    default_connectors_dir: str = Field(default=None, description="Directory for built-in default connectors")
    extension_connectors_dir: str = Field(default=None, description="Directory for generated/user connectors")

    _connector_configs: Dict[str, ConnectorConfig] = {}
    _connector_history_versions: Dict[str, Dict[str, ConnectorConfig]] = {}

    def __init__(
        self,
        base_dir: Optional[str] = None,
        default_connectors_dir: Optional[str] = None,
        extension_connectors_dir: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "connector"))



        _src_dir = Path(__file__).resolve().parent
        # Built-in connectors live in the default/ dir; extension connectors are
        # managed externally (loaded by ExtensionManager into the active version).
        self.default_connectors_dir = default_connectors_dir or str(_src_dir / "default")
        self.extension_connectors_dir = extension_connectors_dir or str(
            path_manager.get(P.EXTENSION_MODULE, module="connector"))

        self._connector_configs: Dict[str, ConnectorConfig] = {}
        self._connector_history_versions: Dict[str, Dict[str, ConnectorConfig]] = {}
        self._instr_cache: Dict[Any, str] = {}

        logger.info(f"| 📁 Connector context manager base directory: {self.base_dir}")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self, connector_names: Optional[List[str]] = None):
        """Discover and load connectors from default and persisted sources.

        Loading only parses ``connector.json`` files (fast, no network). Actions
        declared statically in the JSON are used for prompt display; call
        ``discover()`` to connect to a server and refresh its live action list.

        Args:
            connector_names: If provided, only load these connectors.
        """
        discovered: Dict[str, ConnectorConfig] = {}

        # 1. Load from built-in default directory
        default_configs = await self._load_from_directory(Path(self.default_connectors_dir))
        discovered.update(default_configs)

        # 1b. Load from extension directory (generated/user connectors); extension overrides default
        Path(self.extension_connectors_dir).mkdir(parents=True, exist_ok=True)
        extension_configs = await self._load_from_directory(Path(self.extension_connectors_dir))
        discovered.update(extension_configs)


        # 3. Filter by name if requested
        if connector_names is not None:
            filtered: Dict[str, ConnectorConfig] = {}
            for name in connector_names:
                if name in discovered:
                    filtered[name] = discovered[name]
                else:
                    logger.warning(f"| ⚠️ Requested connector '{name}' not found in discovered connectors")
            discovered = filtered

        # 4. Build text representations, register versions, and store
        for name, connector_config in discovered.items():
            connector_config.text = self._build_text_representation(connector_config)
            self._connector_configs[name] = connector_config

            if name not in self._connector_history_versions:
                self._connector_history_versions[name] = {}
            self._connector_history_versions[name][connector_config.version] = connector_config

            await version_manager.register_version("connector", name, connector_config.version)

            permission_manager.register(
                entity_name=name,
                mode=PermissionMode(connector_config.permission_mode),
            )
            logger.info(f"| 🎯 Connector '{name}' v{connector_config.version} loaded from {connector_config.connector_dir}")

        # 5. Persist
        self._invalidate_instruction()

        logger.info(f"| ✅ Connectors initialization completed — {len(self._connector_configs)} connector(s) loaded")

    # ------------------------------------------------------------------
    # Directory scanning & connector.json parsing
    # ------------------------------------------------------------------

    async def _load_from_directory(self, root_dir: Path) -> Dict[str, ConnectorConfig]:
        """Scan *root_dir* for sub-directories that contain a CONNECTOR.md file."""
        configs: Dict[str, ConnectorConfig] = {}

        if not root_dir.exists():
            logger.info(f"| 📂 Connector directory does not exist, skipping: {root_dir}")
            return configs

        for child in sorted(root_dir.iterdir()):
            if not child.is_dir():
                continue
            connector_md = child / "CONNECTOR.md"
            if not connector_md.exists():
                continue
            try:
                connector_config = self._parse_connector_dir(child)
                configs[connector_config.name] = connector_config
            except Exception as e:
                logger.error(f"| ❌ Failed to parse connector at {child}: {e}")

        return configs

    @staticmethod
    def _resolve_connection(connection: Dict[str, Any], connector_dir: Path) -> Dict[str, Any]:
        """Make a stdio connection config portable across machines/environments.

        CONNECTOR.md should declare the connection relative to the connector, e.g.::

            connection:
              transport: stdio
              command: python
              args:
                - server.py

        This resolves that at load time so the config never needs machine-specific
        absolute paths:

        * ``command`` — any Python interpreter (``python``/``python3`` or an absolute
          ``.../bin/python``) is replaced with ``sys.executable``, i.e. the interpreter
          currently running the framework, so it always matches the active environment.
        * ``args`` — a relative ``*.py`` script is resolved against ``connector_dir``
          (the connector's own directory), so it works wherever the repo is checked out.

        Non-stdio transports (e.g. ``streamable_http`` hosted connectors) are returned
        unchanged.
        """
        conn = dict(connection or {})
        if conn.get("transport") != "stdio":
            return conn

        cmd = str(conn.get("command", "")).strip()
        if cmd and Path(cmd).name.startswith("python"):
            conn["command"] = sys.executable

        resolved_args = []
        for a in (conn.get("args") or []):
            a_str = str(a)
            if a_str.endswith(".py") and not os.path.isabs(a_str):
                resolved_args.append(str((connector_dir / a_str).resolve()))
            else:
                resolved_args.append(a)
        if "args" in conn:
            conn["args"] = resolved_args
        return conn

    def _parse_connector_dir(self, connector_dir: Path) -> ConnectorConfig:
        """Parse a single connector directory (its CONNECTOR.md) into a ConnectorConfig.

        CONNECTOR.md is a YAML frontmatter block (name/description/version/type/
        connection/actions/...) followed by a markdown body (module intro + per-tool
        detailed docs).
        """
        connector_md = connector_dir / "CONNECTOR.md"
        raw = connector_md.read_text(encoding="utf-8")

        frontmatter, body = self._parse_frontmatter(raw)

        name = frontmatter.get("name", connector_dir.name)
        description = frontmatter.get("description", "")
        version = str(frontmatter.get("version", "1.0.0"))
        enable_evolving = str(frontmatter.get("enable_evolving", "false")).lower() == "true"
        type_value = frontmatter.get("type", "worker")
        permission_mode = frontmatter.get("permission_mode", "workspace_write")
        connection = self._resolve_connection(frontmatter.get("connection", {}) or {}, connector_dir)
        actions = list(frontmatter.get("actions", []) or [])
        action_schemas = frontmatter.get("action_schemas", {}) or {}

        reserved = {
            "name", "description", "version", "enable_evolving", "type",
            "permission_mode", "connection", "actions", "action_schemas",
        }
        metadata = {k: v for k, v in frontmatter.items() if k not in reserved}

        return ConnectorConfig(
            name=name,
            description=description,
            metadata=metadata,
            enable_evolving=enable_evolving,
            permission_mode=permission_mode,
            version=version,
            type=type_value,
            connector_dir=str(connector_dir),
            content=body.strip(),
            connection=connection,
            actions=actions,
            action_schemas=action_schemas,
        )

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
        """Split YAML frontmatter (between --- delimiters) from the markdown body.

        Uses a full YAML parser (not line-by-line) because ``connection`` is a
        nested mapping/list.
        """
        pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
        match = pattern.match(text)

        if not match:
            return {}, text

        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as e:
            logger.warning(f"| ⚠️ Failed to parse connector frontmatter: {e}")
            frontmatter = {}
        if not isinstance(frontmatter, dict):
            frontmatter = {}

        body = text[match.end():]
        return frontmatter, body

    @staticmethod
    def _build_text_representation(connector_config: ConnectorConfig) -> str:
        """Build a concise summary for prompt injection (name + description + actions)."""
        parts = [
            f"Connector: {connector_config.name}",
            f"Description: {connector_config.description}",
            f"Type: {connector_config.type}",
            f"Version: {connector_config.version}",
            f"Transport: {connector_config.connection.get('transport', 'unknown')}",
            f"CONNECTOR.md: {os.path.join(connector_config.connector_dir, 'CONNECTOR.md')}",
        ]

        if connector_config.actions:
            parts.append("Actions:")
            for a in connector_config.actions:
                parts.append(f"  - {a}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Register / Update / Unregister / Copy / Restore
    # ------------------------------------------------------------------

    async def register(
        self,
        connector_dir: str,
        override: bool = False,
        version: Optional[str] = None,
        enable_evolving: Optional[bool] = None,
    ) -> ConnectorConfig:
        """Register a connector from a directory containing connector.json.

        Args:
            connector_dir: Path to the connector directory.
            override: If True, overwrite an existing connector with the same name.
            version: Explicit version string. If None, reads from connector.json or auto-generates.
            enable_evolving: If not None, override the frontmatter-parsed evolvability flag
                (newly generated connectors are registered evolvable so they can be optimized later).

        Returns:
            The registered ConnectorConfig.
        """
        connector_dir_path = Path(connector_dir)
        if not (connector_dir_path / "CONNECTOR.md").exists():
            raise FileNotFoundError(f"No CONNECTOR.md found in {connector_dir}")

        connector_config = self._parse_connector_dir(connector_dir_path)
        if enable_evolving is not None:
            connector_config.enable_evolving = enable_evolving

        if version is not None:
            connector_config.version = version
        else:
            existing_version = await version_manager.get_version("connector", connector_config.name)
            if existing_version and connector_config.version == "1.0.0":
                connector_config.version = existing_version

        if connector_config.name in self._connector_configs and not override:
            raise ValueError(
                f"Connector '{connector_config.name}' already registered. Use override=True or update()."
            )

        connector_config.text = self._build_text_representation(connector_config)
        self._connector_configs[connector_config.name] = connector_config

        if connector_config.name not in self._connector_history_versions:
            self._connector_history_versions[connector_config.name] = {}
        self._connector_history_versions[connector_config.name][connector_config.version] = connector_config

        await version_manager.register_version("connector", connector_config.name, connector_config.version)

        self._invalidate_instruction()

        logger.info(f"| 📝 Registered connector: {connector_config.name} v{connector_config.version}")
        return connector_config

    async def update(
        self,
        name: str,
        connector_dir: Optional[str] = None,
        new_version: Optional[str] = None,
        description: Optional[str] = None,
        content: Optional[str] = None,
        connection: Optional[Dict[str, Any]] = None,
        actions: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConnectorConfig:
        """Update an existing connector and create a new version.

        You can either point to a new connector_dir (re-parse CONNECTOR.md) or
        update individual fields (description, content, connection, actions, metadata) in-place.

        Args:
            name: Name of the connector to update.
            connector_dir: If provided, re-parse this directory as the new connector source.
            new_version: Explicit new version. If None, auto-increments patch.
            description: Override description text.
            content: Override CONNECTOR.md body content.
            connection: Override MCP connection config.
            actions: Override the action list.
            metadata: Override metadata dict.

        Returns:
            Updated ConnectorConfig.
        """
        original = self._connector_configs.get(name)
        if original is None:
            raise ValueError(f"Connector '{name}' not found. Use register() first.")

        if connector_dir is not None:
            updated = self._parse_connector_dir(Path(connector_dir))
        else:
            updated = ConnectorConfig(**original.model_dump())

        if description is not None:
            updated.description = description
        if content is not None:
            updated.content = content
        if connection is not None:
            updated.connection = connection
        if actions is not None:
            updated.actions = actions
        if metadata is not None:
            updated.metadata = metadata

        if new_version is None:
            new_version = await version_manager.generate_next_version("connector", name, "patch")
        updated.version = new_version

        updated.text = self._build_text_representation(updated)
        self._connector_configs[name] = updated

        if name not in self._connector_history_versions:
            self._connector_history_versions[name] = {}
        self._connector_history_versions[name][new_version] = updated

        await version_manager.register_version(
            "connector", name, new_version,
            description=description or f"Updated from {original.version}",
        )

        self._invalidate_instruction()

        logger.info(f"| 🔄 Updated connector '{name}' from v{original.version} to v{new_version}")
        return updated

    async def unregister(self, name: str) -> bool:
        """Remove a connector from the active set.

        Args:
            name: Connector name to unregister.

        Returns:
            True if removed, False if not found.
        """
        if name not in self._connector_configs:
            logger.warning(f"| ⚠️ Connector '{name}' not found")
            return False

        version = self._connector_configs[name].version
        del self._connector_configs[name]

        self._invalidate_instruction()

        logger.info(f"| 🗑️ Unregistered connector '{name}' v{version}")
        return True

    async def copy(
        self,
        name: str,
        new_name: Optional[str] = None,
        new_version: Optional[str] = None,
        new_connector_dir: Optional[str] = None,
    ) -> ConnectorConfig:
        """Copy an existing connector, optionally under a new name.

        Args:
            name: Source connector name.
            new_name: Name for the copy. If None, keeps the original name.
            new_version: Version for the copy. If None, auto-generates.
            new_connector_dir: If provided, physically copies the connector directory.

        Returns:
            The new ConnectorConfig.
        """
        original = self._connector_configs.get(name)
        if original is None:
            raise ValueError(f"Connector '{name}' not found")

        if new_name is None:
            new_name = name

        copied = ConnectorConfig(**original.model_dump())
        copied.name = new_name

        if new_connector_dir is not None:
            dest = Path(new_connector_dir)
            if not dest.exists():
                shutil.copytree(original.connector_dir, str(dest))
            copied.connector_dir = str(dest)

        if new_version is None:
            if new_name == name:
                new_version = await version_manager.generate_next_version("connector", new_name, "patch")
            else:
                new_version = await version_manager.get_version("connector", new_name)
        copied.version = new_version

        copied.text = self._build_text_representation(copied)
        self._connector_configs[new_name] = copied

        if new_name not in self._connector_history_versions:
            self._connector_history_versions[new_name] = {}
        self._connector_history_versions[new_name][new_version] = copied

        await version_manager.register_version(
            "connector", new_name, new_version,
            description=f"Copied from {name}@{original.version}",
        )

        self._invalidate_instruction()

        logger.info(f"| 📋 Copied connector '{name}' v{original.version} -> '{new_name}' v{new_version}")
        return copied

    async def restore(self, name: str, version: str) -> Optional[ConnectorConfig]:
        """Restore a specific version of a connector from history.

        Args:
            name: Connector name.
            version: Version string to restore.

        Returns:
            Restored ConnectorConfig, or None if version not found.
        """
        version_map = self._connector_history_versions.get(name, {})
        target = version_map.get(version)
        if target is None:
            logger.warning(f"| ⚠️ Version {version} not found for connector '{name}'")
            return None

        restored = ConnectorConfig(**target.model_dump())
        restored.text = self._build_text_representation(restored)
        self._connector_configs[name] = restored

        version_history = await version_manager.get_version_history("connector", name)
        if version_history:
            if version not in version_history.versions:
                await version_manager.register_version("connector", name, version)
            version_history.current_version = version
        else:
            await version_manager.register_version("connector", name, version)


        logger.info(f"| 🔄 Restored connector '{name}' to v{version}")
        return restored

    # ------------------------------------------------------------------
    # Discovery (connect to the live MCP server and refresh actions)
    # ------------------------------------------------------------------

    async def discover(self, name: str) -> Optional[List[str]]:
        """Connect to a connector's MCP server and refresh its action list.

        Unlike ``initialize`` (which only reads connector.json), this actually
        opens a session to the server. Returns the discovered action names, or
        None if the connector is unknown or the connection fails.
        """
        cfg = self._connector_configs.get(name)
        if cfg is None:
            logger.warning(f"| ⚠️ Connector '{name}' not found")
            return None

        try:
            try:
                from langchain_mcp_adapters.client import MultiServerMCPClient
            except Exception as e:
                logger.error(f"| ❌ Missing MCP dependency: {e}. Install `langchain_mcp_adapters`.")
                return None

            client = MultiServerMCPClient({cfg.name: cfg.connection}, tool_name_prefix=False)
            tools = await client.get_tools(server_name=cfg.name)
            action_names = [getattr(t, "name", None) or "" for t in tools]
            action_names = [a for a in action_names if a]

            cfg.actions = action_names
            cfg.text = self._build_text_representation(cfg)

            self._invalidate_instruction()

            logger.info(f"| 🔎 Connector '{name}' discovered {len(action_names)} action(s)")
            return action_names
        except Exception as e:
            logger.error(f"| ❌ Connector '{name}' discovery failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    async def get(self, connector_name: str) -> Optional[ConnectorConfig]:
        """Get a loaded connector config by name."""
        return self._connector_configs.get(connector_name)

    async def get_info(self, connector_name: str) -> Optional[ConnectorConfig]:
        """Alias for get()."""
        return self._connector_configs.get(connector_name)

    async def list(self) -> List[str]:
        """Return names of all loaded connectors."""
        return list(self._connector_configs.keys())

    # ------------------------------------------------------------------
    # Context generation (for agent prompt)
    # ------------------------------------------------------------------

    async def get_instruction(self, allowlist: Optional[List[str]] = None, types: Optional[List[str]] = None) -> str:
        """Assemble the connector instruction text for prompt injection, on demand.

        `allowlist` (connector names) selects which connectors to include: None = all;
        [] = none; [names] = only those. `types` filters by ``type``. Cached per
        (allowlist, types); invalidated on registry change via `_invalidate_instruction`.
        """
        key = (None if allowlist is None else tuple(allowlist),
               None if types is None else tuple(types))
        if key in self._instr_cache:
            return self._instr_cache[key]
        targets = list(self._connector_configs.keys()) if allowlist is None else allowlist
        parts: List[str] = []
        for name in targets:
            cfg = self._connector_configs.get(name)
            if cfg is None:
                continue
            if types and cfg.type not in types:
                continue
            transport = (cfg.connection or {}).get("transport", "unknown")
            detail = [f"- **CONNECTOR.md**: {os.path.join(cfg.connector_dir, 'CONNECTOR.md')}"]
            if cfg.actions:
                detail.append(f"- **Actions**: {', '.join(cfg.actions)}")
            parts.append(render_capability_card(
                name=cfg.name,
                description=cfg.description or "",
                meta=f"`{transport}` v{cfg.version}",
                body="\n".join(detail),
            ))
        text = "\n\n".join(parts)
        self._instr_cache[key] = text
        return text

    def _invalidate_instruction(self) -> None:
        """Drop cached instructions so the next get_instruction rebuilds."""
        self._instr_cache.clear()

    # ------------------------------------------------------------------
    # Contract (persistent text summary)
    # ------------------------------------------------------------------



    # ------------------------------------------------------------------
    # Persistence (JSON) — with version history
    # ------------------------------------------------------------------

    async def __call__(
        self,
        name: str,
        input: Dict[str, Any],
        ctx: SessionContext = None,
        **kwargs,
    ) -> Response:
        """Execute a connector by routing an ``action``/``args`` call to its MCP server.

        Args:
            name: Connector (MCP server) name.
            input: {"action": <mcp tool name>, "args": <dict payload>}.
            ctx: Connector context.
        """
        connector_config = self._connector_configs.get(name)
        if connector_config is None:
            return Response(
                type=ResponseType.CONNECTOR,
                success=False,
                message=f"Connector '{name}' not found. Available connectors: {list(self._connector_configs.keys())}",
            )

        action = input.get("action")
        args = input.get("args") or {}
        if not action:
            return Response(
                type=ResponseType.CONNECTOR,
                success=False,
                message="Missing 'action' in input. Expected {'action': <mcp tool name>, 'args': {...}}.",
            )

        logger.info(f"| 🎯 Executing connector '{name}' action '{action}' with args: {args}")
        return await self._invoke_mcp(connector_config, action, args)

    async def _invoke_mcp(self, connector_config: ConnectorConfig, action: str, args: Dict[str, Any]) -> Response:
        """Open a session to the MCP server and invoke a single action."""
        try:
            try:
                from langchain_mcp_adapters.client import MultiServerMCPClient
                from langchain_mcp_adapters.tools import load_mcp_tools
            except Exception as e:
                return Response(
                    type=ResponseType.CONNECTOR,
                    success=False,
                    message=f"Missing MCP dependency: {e}. Install `langchain_mcp_adapters` to use connectors.",
                )

            client = MultiServerMCPClient(
                {connector_config.name: connector_config.connection},
                tool_name_prefix=False,
            )

            async with client.session(connector_config.name) as session:
                tools = await load_mcp_tools(
                    session,
                    server_name=connector_config.name,
                    tool_name_prefix=False,
                )
                tool = next((t for t in tools if getattr(t, "name", None) == action), None)
                if tool is None:
                    available = [getattr(t, "name", None) for t in tools]
                    return Response(
                        type=ResponseType.CONNECTOR,
                        success=False,
                        message=f"MCP action not found: {action} (connector={connector_config.name}). Available: {available}",
                    )

                payload = args or {}
                result = await tool.ainvoke(payload)
                msg = self._unwrap_mcp_result(result)

                return Response(
                    type=ResponseType.CONNECTOR,
                    success=True,
                    message=msg,
                    data={"connector": connector_config.name, "action": action, "args": payload},
                )
        except Exception as e:
            logger.error(f"| ❌ Connector call failed: {e}")
            return Response(type=ResponseType.CONNECTOR, success=False, message=f"Connector call failed: {e}")

    @staticmethod
    def _unwrap_mcp_result(result: Any) -> str:
        """Flatten an MCP tool result into a plain string for the agent.

        MCP tools return content blocks like ``[{"type": "text", "text": "..."}]``
        (the inner text is usually JSON). Unwrap that outer envelope so the agent
        sees the payload directly; fall back to a JSON dump / str otherwise.
        """
        def _text_of(block: Any) -> Optional[str]:
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
                return block["text"]
            return None

        if isinstance(result, list):
            texts = [_text_of(b) for b in result]
            if texts and all(t is not None for t in texts):
                return "\n".join(texts)
        else:
            single = _text_of(result)
            if single is not None:
                return single

        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False)
        return str(result)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def cleanup(self):
        """Release all loaded connectors."""
        self._connector_configs.clear()
        self._connector_history_versions.clear()
        logger.info("| 🧹 Connector context manager cleaned up")
