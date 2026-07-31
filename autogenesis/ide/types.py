"""Wire/state models for the browser IDE."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class IdeInstance(BaseModel):
    """One running IDE container, bound to a single gateway session."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    session_id: str = Field(description="Gateway session this IDE edits.")
    owner: str = Field(default="local", description="Owner whose extensions/settings are mounted.")
    upstream: str = Field(description="Base URL of the opensandbox proxy path serving the IDE.")
    base_path: str = Field(default="", description="Sub-path the editor is served under on the UI origin, e.g. /ide/<session>.")
    workspace_root: str = Field(description="Host directory mounted at /workspace.")
    started_at: float = Field(default_factory=time.time)
    last_seen: float = Field(default_factory=time.time, description="Last heartbeat/proxy touch, for idle reaping.")

    #: The live VscodeSandbox handle. Excluded from serialisation.
    sandbox: Optional[Any] = Field(default=None, exclude=True)
    #: Proxy base URL per container port, resolved on first use. Asking
    #: opensandbox to expose a port is a round trip, and a single page load can
    #: fetch dozens of assets, so the mapping is cached for the container's life.
    port_upstreams: Dict[int, str] = Field(default_factory=dict, exclude=True)

    def public(self) -> Dict[str, Any]:
        """Client-visible status (never leaks the internal upstream URL)."""
        return {
            "session_id": self.session_id,
            "running": True,
            # Where the UI embeds this editor, relative to its own origin — the
            # frontend needs no host of its own, so it works over any tunnel.
            "path": f"{self.base_path}/",
            "started_at": self.started_at,
            "idle_seconds": round(time.time() - self.last_seen, 1),
            "workspace_root": self.workspace_root,
        }
