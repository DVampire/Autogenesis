"""TEMPLATE — an environment (a stateful class exposing named actions).

Copy to `extension/environment/{name}/environment.py`, rename the class, and
implement the actions. Pair it with an `ENVIRONMENT.md` manifest (see
`environment_md_template.md`) in the same directory, plus an `__init__.py` that
imports the class so it registers on load.

Key points:
- Each callable is an action declared with `@environment_manager.action(name=..., description=...)`.
- State lives on the instance (that is what makes an environment *stateful*, unlike a
  stateless tool). If the environment serves concurrent sessions, key state by `ctx`.
- Start heavy resources (servers, browsers) in `initialize()`, not `__init__`; release
  them in `cleanup()`.
- If an action returns an image (e.g. a base64 screenshot), it's a *vision* environment —
  say so in ENVIRONMENT.md.
"""

from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field

from autogenesis.environment.server import environment_manager
from autogenesis.environment.types import Environment
from autogenesis.logger import logger
from autogenesis.registry import ENVIRONMENT


@ENVIRONMENT.register_module(force=True)
class MyEnvironment(Environment):
    """One-line purpose — what the environment provides and its actions."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="my_environment")
    description: str = Field(default="What the environment is and when to use it.")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enable_evolving: bool = Field(default=True)

    def __init__(self, base_dir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        if base_dir:
            self.base_dir = base_dir
        # Lightweight in-memory state here; heavy resources go in initialize().
        self._state: Dict[str, Any] = {}

    # ---------------------------------------------------------------- lifecycle
    async def initialize(self) -> None:
        """Start any external resources. Called once before first use."""
        logger.info(f"| 🌱 {self.name} ready")

    async def cleanup(self) -> None:
        """Release resources. Called on shutdown."""
        self._state.clear()
        logger.info(f"| 🧹 {self.name} cleaned up")

    # ---------------------------------------------------------------- actions
    @environment_manager.action(
        name="set_value",
        description="Store a value under a key. Args: key (str), value (str).",
    )
    async def set_value(self, key: str, value: str, **kwargs) -> Dict[str, Any]:
        self._state[key] = value
        return {"success": True, "message": f"set {key}={value}", "data": {"key": key, "value": value}}

    @environment_manager.action(
        name="get_value",
        description="Read the value stored under a key. Args: key (str).",
    )
    async def get_value(self, key: str, **kwargs) -> Dict[str, Any]:
        value = self._state.get(key)
        return {"success": value is not None, "message": f"{key}={value}", "data": {"key": key, "value": value}}
