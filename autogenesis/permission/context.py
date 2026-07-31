"""PermissionContextManager — manages per-entity PermissionEnforcer instances."""
from __future__ import annotations

from typing import Dict, Optional

from .types import (
    PermissionEnforcer,
    PermissionMode,
    PermissionPolicy,
    PermissionRequest,
    ValidationResult,
)


class PermissionContextManager:
    """Registry of PermissionEnforcer instances, keyed by entity name.

    Entities (tools, agents, skills) are registered at build time via
    register(). All subsequent permission checks go through check().
    """

    def __init__(self) -> None:
        self._enforcers: Dict[str, PermissionEnforcer] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        entity_name: str,
        mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
        workspace: str = "",
        policy: Optional[PermissionPolicy] = None,
        override: bool = True,
    ) -> None:
        """Register or update the enforcer for an entity.

        Called by ToolContextManager / AgentContextManager / SkillContextManager
        during build() when permission_mode is present in the entity config.
        """
        if entity_name in self._enforcers and not override:
            return
        self._enforcers[entity_name] = PermissionEnforcer(
            entity_name=entity_name,
            mode=mode,
            workspace=workspace,
            policy=policy or PermissionPolicy(),
        )

    def unregister(self, entity_name: str) -> None:
        """Remove the enforcer for an entity (e.g. on tool teardown)."""
        self._enforcers.pop(entity_name, None)

    def is_registered(self, entity_name: str) -> bool:
        return entity_name in self._enforcers

    def get_mode(self, entity_name: str) -> Optional[PermissionMode]:
        enforcer = self._enforcers.get(entity_name)
        return enforcer.mode if enforcer else None

    # ------------------------------------------------------------------
    # Unified check interface
    # ------------------------------------------------------------------

    def check(
        self,
        name: str,
        input: PermissionRequest,
        **kwargs,
    ) -> ValidationResult:
        """Unified permission check — the only interface tools/agents/skills use.

        Args:
            name:   Entity name (tool name, agent name, skill name).
            input:  PermissionRequest describing the operation.
            **kwargs: Reserved for future context (e.g. session_id).

        Returns:
            ValidationResult with allowed=True/False and optional warning/reason.
        """
        enforcer = self._enforcers.get(name)
        if enforcer is None:
            return ValidationResult.allow()
        return enforcer.check(input, **kwargs)


__all__ = ["PermissionContextManager"]
