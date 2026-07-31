"""GeneralMemorySystem — two-tier per-session memory persisted as JSON.

Shares all structure with FileSystemMemory via TieredMemory; the only
difference is the on-disk format (JSON here, HTML there).
"""

from __future__ import annotations

import json

from pydantic import Field

from autogenesis.memory.default.tiered import TieredMemory, _SessionState
from autogenesis.registry import MEMORY_SYSTEM


@MEMORY_SYSTEM.register_module(force=True)
class GeneralMemorySystem(TieredMemory):
    """Two-tier per-session memory (recent + working) persisted as JSON."""

    name: str = Field(default="general_memory_system")
    description: str = Field(default="Two-tier (recent + working) memory persisted as JSON.")
    file_ext: str = Field(default="memory.json")

    def _render(self, state: _SessionState) -> str:
        return json.dumps(
            {
                "session_id": state.session_id,
                "task": state.task,
                "todos": [t.model_dump() for t in state.todos],
                "flow_steps": [s.model_dump() for s in state.flow_steps],
                "execution_history": {
                    "working_memory": list(state.working),
                    "recent_history": [r.model_dump() for r in state.recent],
                },
                "final_result": state.final_result,
                "result_success": state.result_success,
            },
            ensure_ascii=False,
            indent=2,
        )
