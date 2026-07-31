---
name: plugins
description: "Outside services — OpenAI, Chroma, Tavily, YouTube, Composio — wrapped as plugins. One plugin per service, providing several tools; each tool is a canvas datasource node returning the canonical {message, data, files} envelope."
version: 1.0.0
type: module
category: plugins
requirements: []
metadata: {}
---
# Plugins

A **plugin** wraps one outside service and provides the tools that talk to it.
The shape is the same one `environment` uses — one class exposing many
capabilities:

| Container | Capabilities | Registry entries |
|---|---|---|
| `BrowserEnvironment` | `@action` click / scroll / type / … | 1 |
| `TavilyPlugin` | `TavilySearchTool`, `TavilyExtractTool` | 1 |

The plugin owns whatever its tools share: the credential, an HTTP client, a base
URL. A key is resolved once per plugin instead of once per call, and a
connection pool outlives the request that opened it.

A plugin is never itself a workflow step. Its *tools* surface on the canvas as
`datasource` nodes and are dispatched through `plugin_manager`.

## A plugin is a package

```
default/tavily/
├── PLUGIN.md          # generated manifest: tools, status, credentials, requirements
├── __init__.py        # from .plugin import TavilyPlugin
├── plugin.py          # the one registered class: identity + shared credential/client
├── resources/icon.svg
└── tools/
    ├── search.py      # class TavilySearchTool(PluginTool)
    └── extract.py     # class TavilyExtractTool(PluginTool)
```

One tool per file, one class per tool — the same layout `tool/default/` uses.

```python
# plugin.py
from .tools.extract import TavilyExtractTool
from .tools.search import TavilySearchTool

@PLUGIN.register_module(force=True)
class TavilyPlugin(Plugin):
    tools = (TavilySearchTool, TavilyExtractTool)

    name: str = "tavily"
    display_name: str = "Tavily"
    category: str = "data"
```

Adding a plugin means adding one line to `default/__init__.py`; that import is
what runs the `@PLUGIN.register_module` decorator, so the file doubles as the
registry's manifest. (Explicit, like `tool/default/__init__.py` — not a
`pkgutil` scan, so a broken package fails loudly at import instead of vanishing
from the palette.)

## Addressing and dispatch

A tool is addressed as `<plugin>.<tool>`:

```
canvas node / workflow datasource step  →  target "tavily.tavily_search"
  → plugin_manager splits on the dot
  → TavilyPlugin.invoke("tavily_search", query=…)
  → TavilySearchTool(query=…)  →  Response
```

A bare plugin name works too, and falls through to the plugin's only tool — so a
single-capability plugin such as `yahoo` keeps a natural target.

## Module layout

| File | Holds |
|---|---|
| `types.py` | `Plugin`, `PluginTool`, `PluginConfig`, `PluginContext`, and the family templates |
| `context.py` | `PluginContextManager` — registry → `PluginConfig` → instance, lifecycle, dispatch |
| `server.py` | `PluginManagerServer` — the thin façade the rest of the framework calls |

Same split as `tool` / `environment` / `connector`. Plugins wrap third-party
services, so the evolution half of those managers (`update` / `copy` /
`restore`) has no counterpart here: rewriting a vendor's API adapter at runtime
is not something the optimizer should do.

## Family templates

Many services differ only in which client object gets constructed. `types.py`
holds that loop once, so a concrete tool supplies only the provider-specific
part — usually a single `_model` or `_build` method:

`LLMPluginTool` · `EmbeddingPluginTool` · `RerankPluginTool` ·
`VectorStorePluginTool` · `MemoryPluginTool` · `ComposioPluginTool`

## Status is computed, not declared

`PluginTool.status` is derived from whether the class (or a family template it
builds on) actually overrides `__call__`. It used to be a hand-written field,
which meant a manifest could claim a tool worked when it only inherited the
stub. A tool that is registered but unimplemented still appears on the canvas
and returns a clear "not implemented yet" when run.

## Dependencies

Provider SDKs are imported lazily inside `__call__`, so a plugin registers
without them and a call returns a clear failed result until they are installed.
Each `PLUGIN.md` lists what that package needs under `requirements:`, and the
credentials it reads under `credentials:` — both generated from the code, so
they cannot drift from it.
