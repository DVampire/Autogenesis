"""E2B sandbox manager (scaffold — not yet implemented).

Sibling of ``autogenesis/sandbox/`` (OpenSandbox). When implemented, this module will
back the same :class:`~autogenesis.sandbox.types.Sandbox` contract with the E2B
code-interpreter SDK (``e2b_code_interpreter``), and register its handles with
the ``E2B`` registry.

TODO: implement E2BSandbox(Sandbox) in autogenesis/e2b/default/ and wire acquire().
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class E2BManagerServer(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    async def initialize(self) -> None:  # pragma: no cover - scaffold
        return None

    async def acquire(self, *args: Any, **kwargs: Any):  # pragma: no cover - scaffold
        raise NotImplementedError(
            "autogenesis.e2b is a scaffold. Implement E2BSandbox in autogenesis/e2b/default/ first. "
            "Use autogenesis.sandbox (OpenSandbox) for now."
        )

    async def cleanup(self) -> None:  # pragma: no cover - scaffold
        return None


e2b_manager = E2BManagerServer()
