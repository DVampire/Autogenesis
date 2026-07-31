"""Deploy tool — run a web service (static site / SPA / API) in a sandbox and get a URL.

Thin LLM-facing verb over ``deployment_manager``. Each site is an isolated
container bound to its own URL; multiple sites coexist (keyed by ``site_id``).
The per-framework knowledge lives in pluggable deploy *profiles* (``runtime``),
so this tool stays stable as new target types are added.
"""

from typing import Any, Dict, List

from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.deploy import deployment_manager, DeployRequest
from autogenesis.logger import logger
from autogenesis.registry import TOOL

_DESCRIPTION = "Deploy and manage web services (static/SPA/API) in isolated sandboxes, each bound to its own URL."

_INSTRUCTION = """
## Function
Deploy a web service into an isolated sandbox container and bind it to a reachable URL, and manage deployed sites. Each site is one container keyed by `site_id`; deploy many and each gets its own URL.

## Actions (pass `action`)
- `deploy`: build + start a site, return its URL. Args:
  - `site_id` (str, required): stable id / reuse key for the site.
  - `runtime` (str): one of `static` (plain HTML/CSS/JS or a pre-built SPA), `node` (build a React/Vue/Vite app and serve it), `python` (FastAPI/Flask/ASGI via uvicorn), `custom` (you supply image/build/start in `overrides`), `llm` (NOT implemented yet). Default `static`.
  - `source_dir` (str, optional): host directory uploaded into the container.
  - `git_url` (str, optional): repo cloned inside the container instead of uploading.
  - `port` (int, optional): override the profile's default port.
  - `env` (dict, optional): environment variables.
  - `overrides` (dict, optional): field-level spec overrides — `image`, `build` (list of shell cmds), `start` (server cmd, MUST bind 0.0.0.0:$PORT), `workspace_root`, `health` ({type: http|command|none, path, command, timeout_s}). `custom` runtime REQUIRES `overrides.start`.
- `list`: list all sites with status + URL. No args.
- `get`: one site's full record. Args: `site_id`.
- `stop`: stop a site's container. Args: `site_id`.
- `redeploy`: tear down and rebuild a site from its stored request (URL may change). Args: `site_id`.

## Guidance
- The service MUST listen on `0.0.0.0` (not `127.0.0.1`) or the URL won't be reachable.
- `static` serves the uploaded directory; for `node`, put a buildable project (has package.json) as source; for `python`, default entrypoint is `app:app` — override `start` for a different one (e.g. `uvicorn main:app --host 0.0.0.0 --port 8000`).
- Backend is automatic: uses the isolated opensandbox (Docker) sandbox when a container runtime is available, else falls back to running on the host directly (no isolation). Force it with the `DEPLOY_BACKEND` env var (`sandbox` | `host` | `auto`). On the host backend, run distinct sites on distinct ports.

## Example
{"name": "deploy_tool", "args": {"action": "deploy", "site_id": "coffee-shop", "runtime": "static", "source_dir": "/abs/path/to/site"}}
"""


@TOOL.register_module(force=True)
class DeployTool(Tool):
    """Deploy/manage sandboxed web services, each bound to a URL."""

    name: str = "deploy_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="danger_full_access", description="Runs build/start commands inside an isolated sandbox.")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    @staticmethod
    def _site_line(rec) -> str:
        """Format one deployment record as a tab-separated line for the `list` view.

        Columns: site id, runtime, status, and URL (or "-" when not yet assigned).
        """
        return f"{rec.site_id}\t{rec.runtime}\t{rec.status.value}\t{rec.url or '-'}"

    async def __call__(self, action: str = "list", **kwargs) -> Response:
        action = (action or "list").lower().strip()
        try:
            if action == "deploy":
                req = DeployRequest(
                    site_id=kwargs["site_id"],
                    runtime=kwargs.get("runtime", "static"),
                    source_dir=kwargs.get("source_dir"),
                    git_url=kwargs.get("git_url"),
                    port=kwargs.get("port"),
                    env=kwargs.get("env") or {},
                    overrides=kwargs.get("overrides") or {},
                )
                rec = await deployment_manager.deploy(req)
                ok = rec.status.value == "running"
                msg = (f"✅ '{rec.site_id}' deployed at {rec.url}" if ok
                       else f"❌ '{rec.site_id}' status={rec.status.value}: {rec.error}")
                return Response(type=ResponseType.TOOL, success=ok, message=msg, data=rec.model_dump())

            if action == "list":
                sites = await deployment_manager.list_sites()
                if not sites:
                    return Response(type=ResponseType.TOOL, success=True, message="No deployed sites.")
                body = "\n".join(["site_id\truntime\tstatus\turl"] + [self._site_line(s) for s in sites])
                return Response(type=ResponseType.TOOL, success=True, message=body,
                                data={"sites": [s.model_dump() for s in sites]})

            if action == "get":
                rec = await deployment_manager.get_site(kwargs["site_id"])
                if rec is None:
                    return Response(type=ResponseType.TOOL, success=False, message=f"No such site {kwargs['site_id']!r}.")
                return Response(type=ResponseType.TOOL, success=True, message=self._site_line(rec), data=rec.model_dump())

            if action == "stop":
                rec = await deployment_manager.stop_site(kwargs["site_id"])
                return Response(type=ResponseType.TOOL, success=True, message=f"Stopped '{rec.site_id}'.", data=rec.model_dump())

            if action == "redeploy":
                rec = await deployment_manager.redeploy(kwargs["site_id"])
                ok = rec.status.value == "running"
                msg = (f"✅ '{rec.site_id}' redeployed at {rec.url}" if ok
                       else f"❌ redeploy '{rec.site_id}' status={rec.status.value}: {rec.error}")
                return Response(type=ResponseType.TOOL, success=ok, message=msg, data=rec.model_dump())

            return Response(type=ResponseType.TOOL, success=False,
                            message=f"Unknown action {action!r}. Use deploy | list | get | stop | redeploy.")
        except KeyError as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Missing required arg: {e}")
        except Exception as e:
            logger.error(f"| ❌ deploy_tool {action} failed: {e}")
            return Response(type=ResponseType.TOOL, success=False, message=f"Error: {e}")
