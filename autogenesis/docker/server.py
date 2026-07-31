"""Docker sandbox manager (scaffold — not yet implemented).

Sibling of ``autogenesis/sandbox/`` (OpenSandbox). When implemented, this module will
back the same :class:`~autogenesis.sandbox.types.Sandbox` contract with a plain Docker
runtime (containers + exec + file copy), and register its handles with the
``DOCKER`` registry.

TODO: implement DockerSandbox(Sandbox) in autogenesis/docker/default/ and wire acquire().
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class DockerManagerServer(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    async def initialize(self) -> None:  # pragma: no cover - scaffold
        return None

    async def acquire(self, *args: Any, **kwargs: Any):  # pragma: no cover - scaffold
        raise NotImplementedError(
            "autogenesis.docker is a scaffold. Implement DockerSandbox in autogenesis/docker/default/ first. "
            "Use autogenesis.sandbox (OpenSandbox) for now."
        )

    async def cleanup(self) -> None:  # pragma: no cover - scaffold
        return None


docker_manager = DockerManagerServer()
