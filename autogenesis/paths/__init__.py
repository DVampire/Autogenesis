"""Single source of truth for the on-disk layout.

    from autogenesis.paths import P, path_manager
    path_manager.get(P.SESSION_WORKSPACE, owner="local", session_id=sid)

Two roots only: ``output/`` for generated, machine- and user-specific state, and
``extension/`` for shared, durable components.
"""

from .server import PathManagerServer, path_manager
from .types import LAYOUT, P

__all__ = ["path_manager", "PathManagerServer", "P", "LAYOUT"]
