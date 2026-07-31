"""Browser IDE: one VS Code container per gateway session.

Human-facing, like the canvas — the agent never calls into this module and the
IDE is not registered as a capability.
"""

from .server import IdeManagerServer, ide_manager
from .types import IdeInstance

__all__ = ["ide_manager", "IdeManagerServer", "IdeInstance"]
