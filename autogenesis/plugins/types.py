"""Type definitions for the plugins module.

A **plugin** wraps one outside service — Tavily, OpenAI, Chroma, Yahoo — and
provides the tools that talk to it. The shape mirrors :class:`Environment`,
which is one class exposing many actions:

===================  ==================================  ==================
Container            Capabilities                        Registry entries
===================  ==================================  ==================
``BrowserEnvironment``  ``@action`` click / scroll / …    1
``TavilyPlugin``        ``TavilySearchTool``, …           1
===================  ==================================  ==================

The plugin owns whatever the tools share: credentials, an HTTP client, a base
URL. Tools read those through the plugin instead of each resolving its own, so
a key is looked up once per plugin rather than once per tool.

Tools live one-class-per-file under ``tools/``, matching how ``tool/default/``
is laid out. A plugin declares the classes it provides and the base binds them::

    from .tools.search import TavilySearchTool
    from .tools.extract import TavilyExtractTool

    @PLUGIN.register_module()
    class TavilyPlugin(Plugin):
        name = "tavily"
        display_name = "Tavily"
        tools = (TavilySearchTool, TavilyExtractTool)

A tool is addressed as ``<plugin>.<tool>`` — ``tavily.tavily_search``. That id
is what canvas nodes and workflow ``datasource`` steps carry as their target;
``plugin_manager`` splits on the dot and dispatches through the plugin.

A plugin is never itself a workflow step. Its tools surface on the canvas as
``datasource`` nodes (:class:`StepType.DATASOURCE`), and every one returns the
canonical ``{message, data, files}`` :class:`Response` envelope so its output
composes with any other capability.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar, Dict, List, Optional, Sequence, Type

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from autogenesis.session import BaseContext
from autogenesis.response.types import Response, ResponseType


class PluginContext(BaseContext):
    """Context passed into the plugin manager and individual plugin instances."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Unique identifier for this plugin call.")
    name: str = Field(default="", description="Name of the plugin being called.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload passed to the plugin.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this context.")


#: Where a plugin's preserved SVG lives, relative to its package dir.
ICON_FILE = os.path.join("resources", "icon.svg")


class PluginConfig(BaseModel):
    """A registered plugin: its class, its settings, and its live instance.

    The same split :class:`EnvironmentConfig` makes — the registry hands over a
    *class*, the config file supplies its settings, and the instance is built
    from the two on first use. ``tools`` mirrors ``EnvironmentConfig.actions``:
    the capabilities the container provides.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="The name of the plugin")
    display_name: str = Field(default="", description="Human label for the palette")
    description: str = Field(default="", description="The description of the plugin")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="The metadata of the plugin")
    version: str = Field(default="1.0.0", description="Version of the plugin")
    enable_evolving: bool = Field(default=False, description="Whether the plugin may be evolved (self-optimized)")

    cls: Optional[Type["Plugin"]] = Field(default=None, description="The class of the plugin")
    config: Optional[Dict[str, Any]] = Field(default={}, description="The initialization configuration of the plugin")
    instance: Optional[Any] = Field(default=None, description="The instance of the plugin")
    code: Optional[str] = Field(default=None, description="Source code of the plugin's module")
    path: Optional[str] = Field(default=None, description="File the plugin class is defined in")

    tools: Dict[str, "PluginTool"] = Field(default_factory=dict, description="Tools this plugin provides, by short name")

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Serialise without the live instance (which is not JSON-safe)."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "metadata": self.metadata,
            "version": self.version,
            "enable_evolving": self.enable_evolving,
            "cls": self.cls.__name__ if self.cls else None,
            "config": self.config,
            "instance": None,
            "code": self.code,
            "path": self.path,
            "tools": {name: tool.public() for name, tool in self.tools.items()},
        }


class PluginTool(BaseModel):
    """One capability of a plugin — one class per file under ``tools/``.

    Subclasses set ``name`` (short, unique within the plugin), ``display_name``
    and ``description``, then override :meth:`__call__`. Until they do, the
    inherited stub returns a clear failure: the node stays visible in the
    palette but honestly reports that it does nothing yet.

    Credentials come from the owning plugin via :meth:`_secret`, so a tool never
    needs to know how its provider's key is configured.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="", description="Short id, unique within the plugin (e.g. ``tavily_search``).")
    display_name: str = Field(default="", description="Human label for the palette (e.g. ``Tavily Search API``).")
    description: str = Field(default="", description="One-line description of what the tool does.")
    #: Palette section. Left empty to inherit the plugin's, because one service
    #: often spans several: OpenAI provides both a chat model (``agent``) and an
    #: embedding model (``knowledge``).
    category: str = Field(default="", description="Palette section; empty inherits the plugin's.")
    type: str = Field(default="", description="Capability family (model / embedding / …); empty inherits the plugin's.")

    #: Set by :meth:`Plugin.bind`. Private so pydantic does not try to serialise
    #: the plugin and its tools into each other in a cycle.
    _owner: Optional["Plugin"] = PrivateAttr(default=None)

    # -------------------------------------------------------------- identity
    def bind(self, plugin: "Plugin") -> "PluginTool":
        """Attach this tool to its plugin. Called once, at plugin construction."""
        self._owner = plugin
        return self

    @property
    def owner(self) -> Optional["Plugin"]:
        """The plugin providing this tool, or None if it was built standalone."""
        return self._owner

    @property
    def id(self) -> str:
        """Fully qualified address: ``<plugin>.<tool>``."""
        owner = self._owner
        return f"{owner.name}.{self.name}" if owner is not None and owner.name else self.name

    @property
    def implemented(self) -> bool:
        """Whether this tool actually does anything yet.

        Read off the class rather than declared: ``status: str = "complete"``
        used to be hand-written, and 63 of the 244 tools claimed it while still
        inheriting the stub. A tool counts as implemented once it — or one of
        the family templates it is built on — overrides :meth:`__call__`.
        """
        return type(self).__call__ is not PluginTool.__call__

    @property
    def status(self) -> str:
        """``complete`` or ``stub``, derived from :attr:`implemented`."""
        return "complete" if self.implemented else "stub"

    def public(self) -> Dict[str, Any]:
        """Everything the canvas catalog needs to build this tool's node."""
        owner = self._owner
        plugin_id = owner.name if owner is not None else ""
        return {
            "id": self.id,
            "tool": self.name,
            "plugin": plugin_id,
            "plugin_label": (owner.display_name or owner.name) if owner is not None else "",
            "display_name": self.display_name or self.name,
            "description": self.description,
            "category": self.category or (owner.category if owner is not None else "data"),
            "icon": f"plugin:{plugin_id}" if plugin_id else "",
            "status": self.status,
        }

    def _label(self) -> str:
        """Human name of the owning plugin, for user-facing messages."""
        owner = self._owner
        return (owner.display_name or owner.name) if owner is not None else self.name

    # ------------------------------------------------------------- responses
    def _secret(self, arg_value: Any = "", *env_names: str) -> str:
        """Resolve a credential through the owning plugin (see :meth:`Plugin.secret`)."""
        if self._owner is not None:
            return self._owner.secret(arg_value, *env_names)
        return _resolve_secret("", arg_value, *env_names)

    @staticmethod
    def _ok(message: str, **data: Any) -> Response:
        """Canonical success envelope."""
        return Response(type=ResponseType.TOOL, success=True, message=message, data=data)

    @staticmethod
    def _fail(message: str) -> Response:
        """Canonical failure envelope (bad input / provider error)."""
        return Response(type=ResponseType.TOOL, success=False, message=message)

    def _stub(self) -> Response:
        """Uniform response for a tool that is registered but not implemented."""
        return Response(
            type=ResponseType.TOOL,
            success=False,
            message=f"{self.id}: this {self._label()} tool is registered but not implemented yet.",
            data={"plugin": self._owner.name if self._owner else "", "tool": self.name, "status": self.status},
        )

    async def __call__(self, **kwargs) -> Response:  # noqa: D401 — stub by default
        return self._stub()


def _resolve_secret(plugin_name: str, arg_value: Any = "", *env_names: str) -> str:
    """Explicit argument → ``config[<plugin>_plugin]`` block → environment variable."""
    if arg_value:
        return str(arg_value).strip()
    if plugin_name:
        try:
            from autogenesis.config import config

            cfg = config.get(f"{plugin_name}_plugin", {}) or {}
            for key in ("api_key", "apikey", "token", "key"):
                if cfg.get(key):
                    return str(cfg[key]).strip()
        except Exception:  # noqa: BLE001 — config is best-effort
            pass
    for env in env_names:
        value = os.environ.get(env)
        if value:
            return value.strip()
    return ""


class Plugin(BaseModel):
    """One outside service, and the tools that talk to it.

    Subclasses declare their identity and the tool classes they provide::

        class TavilyPlugin(Plugin):
            name = "tavily"
            display_name = "Tavily"
            tools = (TavilySearchTool, TavilyExtractTool)

    The base instantiates and binds each one, so ``plugin.tool("tavily_search")``
    returns a live tool and ``await plugin("tavily_search", query="…")``
    dispatches to it.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    #: Tool classes this plugin provides. A ClassVar, so it is a declaration the
    #: author writes rather than per-instance state; the bound instances live in
    #: the private map behind :meth:`tool`.
    tools: ClassVar[Sequence[Type[PluginTool]]] = ()

    name: str = Field(default="", description="Registered plugin id (e.g. ``tavily``).")
    display_name: str = Field(default="", description="Human label (e.g. ``Tavily``).")
    description: str = Field(default="", description="One-line description of the service.")
    #: Which palette section this plugin's tools belong to (data / tool / agent / knowledge).
    category: str = Field(default="data", description="Palette section for this plugin's tools.")
    type: str = Field(default="data_source", description="Plugin family: data_source / software / …")
    instruction: str = Field(default="", description="Full usage instruction, fetched on demand.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary plugin metadata.")
    permission_mode: str = Field(default="read_only", description="Permission mode for this plugin's side effects.")

    _tools: Dict[str, PluginTool] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _bind_tools(self) -> "Plugin":
        """Instantiate and bind the declared tool classes."""
        for tool_cls in type(self).tools:
            tool = tool_cls()
            tool.bind(self)
            self._tools[tool.name] = tool
        md: Dict[str, Any] = dict(self.metadata or {})
        md.setdefault("canvas_category", self.category)
        md.setdefault("plugin", self.name)
        md.setdefault("plugin_label", self.display_name or self.name)
        md.setdefault("icon", f"plugin:{self.name}" if self.name else None)
        self.metadata = md
        return self

    # ----------------------------------------------------------- tool access
    def tool(self, name: str) -> Optional[PluginTool]:
        """One bound tool by its short name, or None."""
        return self._tools.get(name)

    def tool_list(self) -> List[PluginTool]:
        """Every bound tool, in declaration order."""
        return list(self._tools.values())

    # -------------------------------------------------------------- dispatch
    async def invoke(self, tool: str = "", /, **kwargs) -> Response:
        """Run one of this plugin's tools.

        ``tool`` is positional-only so a tool of its own may take a parameter
        literally named ``tool`` without colliding with the dispatch argument.
        """
        if not self._tools:
            return Response(type=ResponseType.TOOL, success=False,
                            message=f"Plugin '{self.name}' provides no tools.")
        target = self._tools.get(tool) if tool else None
        if target is None:
            if tool:
                known = ", ".join(sorted(self._tools)) or "none"
                return Response(type=ResponseType.TOOL, success=False,
                                message=f"Plugin '{self.name}' has no tool '{tool}' (known: {known}).")
            if len(self._tools) > 1:
                known = ", ".join(sorted(self._tools))
                return Response(type=ResponseType.TOOL, success=False,
                                message=f"Plugin '{self.name}' needs a tool name (one of: {known}).")
            target = next(iter(self._tools.values()))
        return await target(**kwargs)

    async def __call__(self, tool: str = "", /, **kwargs) -> Response:
        """Unified entry point — an alias of :meth:`invoke`."""
        return await self.invoke(tool, **kwargs)

    # ------------------------------------------------------------ shared use
    def secret(self, arg_value: Any = "", *env_names: str) -> str:
        """Resolve this plugin's credential, shared by all of its tools.

        Explicit argument → ``config[<plugin>_plugin]`` block → environment
        variable. Resolved once per plugin rather than once per tool.
        """
        return _resolve_secret(self.name, arg_value, *env_names)

    async def initialize(self) -> None:
        """Optional async setup (open API clients, read credentials)."""

    async def cleanup(self) -> None:
        """Optional teardown of any provider resources."""


# ---------------------------------------------------------------------------
# Family templates.
#
# Many services differ only in which client object gets constructed: every
# OpenAI-compatible chat endpoint runs the same prompt → invoke → text loop,
# every langchain vector store the same embed → build → ingest → search loop.
# These hold that loop once, so a concrete tool supplies only the part that is
# genuinely provider-specific — usually a single ``_model`` / ``_build`` method.
# ---------------------------------------------------------------------------


class LLMPluginTool(PluginTool):
    """Prompt → generated text, for a chat-completion service."""

    category: str = "agent"

    #: OpenAI-compatible endpoint defaults, used by :meth:`_openai_compatible`.
    default_base_url: str = ""
    key_env: str = ""

    def _openai_compatible(self, model: str, api_key: str = "", base_url: str = "",
                           temperature: float = 0.1, **kw: Any) -> Any:
        """Build a ChatOpenAI pointed at an OpenAI-compatible endpoint."""
        from langchain_openai import ChatOpenAI  # noqa: PLC0415

        key = self._secret(api_key, *([self.key_env] if self.key_env else []), "OPENAI_API_KEY")
        if not key:
            raise ValueError(f"no API key (set api_key or {self.key_env or 'OPENAI_API_KEY'}).")
        return ChatOpenAI(model=model, api_key=key,
                          base_url=(base_url or self.default_base_url or None),
                          temperature=temperature, **kw)

    def _model(self, **cfg: Any) -> Any:  # pragma: no cover - overridden
        """Construct the provider's langchain chat model. Subclasses implement."""
        raise NotImplementedError

    async def _generate(self, prompt: str = "", **cfg: Any) -> Response:
        """Build the model → invoke(prompt) → return generated text."""
        prompt = str(prompt or cfg.pop("input_value", "") or "").strip()
        if not prompt:
            return self._fail(f"{self.id}: 'prompt' is required.")
        try:
            model = self._model(**cfg)
            result = model.invoke(prompt)
            text = result.content if hasattr(result, "content") else str(result)
        except Exception as exc:  # noqa: BLE001 — missing SDK / bad key / provider error
            return self._fail(f"{self.id}: {type(exc).__name__}: {exc}")
        return self._ok(str(text), text=str(text), model=cfg.get("model_name") or cfg.get("model"))


class VectorStorePluginTool(PluginTool):
    """Ingest texts and/or run a similarity search against a vector store."""

    category: str = "knowledge"

    #: Some backends (Vectara, Upstash's built-in model) embed server-side and
    #: need no external Embeddings model.
    needs_embedding: bool = True

    def _embedding(self, spec: str = "") -> Any:
        """Resolve an Embeddings model.

        ``spec`` may name a provider/model as ``openai:text-embedding-3-small``;
        by default OpenAI embeddings keyed by ``OPENAI_API_KEY`` (or the
        ``openai_plugin`` config block). Raises ``ValueError`` with a clear
        message if none can be built.
        """
        provider, _, model = (spec or "").partition(":")
        provider = (provider or "openai").strip().lower()
        if provider == "openai":
            key = self._secret("", "OPENAI_API_KEY")
            if not key:
                raise ValueError("no embedding available (set OPENAI_API_KEY or pass embedding='provider:model').")
            from langchain_openai import OpenAIEmbeddings  # noqa: PLC0415

            return OpenAIEmbeddings(model=model or "text-embedding-3-small", api_key=key)
        raise ValueError(f"unsupported embedding provider '{provider}' (try 'openai:<model>').")

    def _build(self, embedding: Any, **conn: Any) -> Any:  # pragma: no cover - overridden
        """Construct the backend langchain vector store. Subclasses implement."""
        raise NotImplementedError

    async def _run(self, query: str = "", texts: Optional[List[str]] = None,
                   embedding: str = "", k: int = 4, **conn: Any) -> Response:
        """Resolve embedding → build store → optional ingest → similarity search."""
        query = str(query or "").strip()
        texts = [t for t in (texts or []) if str(t).strip()]
        if not query and not texts:
            return self._fail(f"{self.id}: provide 'query' to search or 'texts' to ingest.")
        emb = None
        if self.needs_embedding:
            try:
                emb = self._embedding(embedding)
            except Exception as exc:  # noqa: BLE001
                return self._fail(f"{self.id}: {exc}")
        try:
            store = self._build(emb, **conn)
            ingested = 0
            if texts:
                store.add_texts(texts)
                ingested = len(texts)
            records = []
            if query:
                for doc in store.similarity_search(query, k=int(k)):
                    records.append({"content": doc.page_content, "metadata": getattr(doc, "metadata", {})})
        except Exception as exc:  # noqa: BLE001 — missing lib / unreachable store / bad creds
            return self._fail(f"{self.id}: {type(exc).__name__}: {exc}")
        msg = []
        if ingested:
            msg.append(f"ingested {ingested} text(s)")
        if query:
            msg.append(f"found {len(records)} match(es) for '{query}'")
        return self._ok(f"{self._label()}: " + ", ".join(msg) + ".",
                        query=query, records=records, count=len(records), ingested=ingested)


class EmbeddingPluginTool(PluginTool):
    """Text → vector."""

    category: str = "knowledge"

    key_env: str = ""
    default_base_url: str = ""

    def _embeddings(self, **cfg: Any) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    async def _embed(self, text: str = "", **cfg: Any) -> Response:
        text = str(text or cfg.pop("input_value", "") or "").strip()
        if not text:
            return self._fail(f"{self.id}: 'text' is required.")
        try:
            model = self._embeddings(**cfg)
            vector = model.embed_query(text)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{self.id}: {type(exc).__name__}: {exc}")
        vector = list(vector)
        return self._ok(f"{self._label()}: embedded text into a {len(vector)}-dim vector.",
                        vector=vector, dims=len(vector))


class RerankPluginTool(PluginTool):
    """Query + documents → documents reordered by relevance."""

    category: str = "knowledge"

    key_env: str = ""

    def _reranker(self, **cfg: Any) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    async def _rerank(self, query: str = "", documents: Optional[List[str]] = None,
                      top_n: int = 3, **cfg: Any) -> Response:
        query = str(query or "").strip()
        documents = [str(d) for d in (documents or []) if str(d).strip()]
        if not query or not documents:
            return self._fail(f"{self.id}: 'query' and non-empty 'documents' are required.")
        try:
            from langchain_core.documents import Document  # noqa: PLC0415

            compressor = self._reranker(top_n=int(top_n), **cfg)
            docs = [Document(page_content=d) for d in documents]
            ranked = compressor.compress_documents(documents=docs, query=query)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{self.id}: {type(exc).__name__}: {exc}")
        records = [{"content": d.page_content,
                    "score": (d.metadata or {}).get("relevance_score")} for d in ranked]
        return self._ok(f"{self._label()}: reranked to {len(records)} document(s) for '{query}'.",
                        query=query, records=records, count=len(records))


class MemoryPluginTool(PluginTool):
    """Chat-memory backend: read the message history, or append to it."""

    category: str = "agent"

    def _history(self, session_id: str, **cfg: Any) -> Any:  # pragma: no cover - overridden
        """Build a langchain BaseChatMessageHistory for the session. Subclasses implement."""
        raise NotImplementedError

    async def _memory(self, action: str = "get", session_id: str = "default",
                      message: str = "", role: str = "user", **cfg: Any) -> Response:
        action = (action or "get").strip().lower()
        try:
            history = self._history(session_id, **cfg)
            if action == "add":
                if not message.strip():
                    return self._fail(f"{self.id}: 'message' is required to add.")
                if role == "ai":
                    history.add_ai_message(message)
                else:
                    history.add_user_message(message)
                return self._ok(f"{self._label()}: added {role} message to '{session_id}'.",
                                session_id=session_id)
            records = [{"role": getattr(m, "type", "message"), "content": m.content}
                       for m in getattr(history, "messages", [])]
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{self.id}: {type(exc).__name__}: {exc}")
        return self._ok(f"{self._label()}: {len(records)} message(s) in '{session_id}'.",
                        session_id=session_id, records=records, count=len(records))


class ComposioPluginTool(PluginTool):
    """Execute a Composio action against one connected app."""

    category: str = "tool"

    #: Composio toolkit slug. The plugin sets it once for all of its tools.
    app_name: str = ""

    async def __call__(self, action: str = "", arguments: Optional[Dict[str, Any]] = None,
                       api_key: str = "", entity_id: str = "default", **kwargs) -> Response:
        key = self._secret(api_key, "COMPOSIO_API_KEY")
        if not key:
            return self._fail(f"{self.id}: no Composio API key (set api_key or COMPOSIO_API_KEY).")
        action = str(action or "").strip()
        if not action:
            return self._fail(
                f"{self.id}: 'action' is required (a Composio action slug for the "
                f"'{self.app_name}' app, e.g. {self.app_name.upper()}_...).")
        try:
            from composio import Composio  # noqa: PLC0415

            client = Composio(api_key=key)
            result = client.tools.execute(action, arguments=arguments or {}, user_id=entity_id)
        except Exception as exc:  # noqa: BLE001 — missing SDK / auth / action error
            return self._fail(f"{self.id}: {type(exc).__name__}: {exc}")
        return self._ok(f"{self._label()}: executed '{action}'.", app=self.app_name,
                        action=action, result=result)


__all__ = [
    "Plugin", "PluginConfig", "PluginContext", "PluginTool", "ICON_FILE",
    "LLMPluginTool", "VectorStorePluginTool", "EmbeddingPluginTool",
    "RerankPluginTool", "MemoryPluginTool", "ComposioPluginTool",
]
