from typing import Any
from pydantic import Field

from autogenesis.memory.default.tiered import TieredMemory, _SessionState
from autogenesis.registry import MEMORY_SYSTEM

@MEMORY_SYSTEM.register_module(force=True)
class ConstraintMemory(TieredMemory):
    name: str = Field(default="constraint_memory")
    description: str = Field(default="Retains confirmed constraints verbatim, alongside chronological tiers.")
    enable_evolving: bool = Field(default=True)

    def _render(self, state: _SessionState) -> str:
        constraints = []
        recent = []
        
        for r in state.recent:
            text = r.as_line().lower()
            if "constraint" in text or "established" in text or "verified fact" in text:
                constraints.append(r.as_line())
            else:
                recent.append(r.as_line())
                
        lines = []
        
        if state.working:
            lines.append("## Working Memory")
            lines.extend(f"- {s}" for s in state.working)
            lines.append("")
            
        if constraints:
            lines.append("## Confirmed constraints")
            lines.extend(constraints)
            lines.append("")
            
        if recent:
            lines.append("## Recent Steps")
            lines.extend(recent)
            lines.append("")
            
        if state.final_result:
            lines.append("## Final Result")
            lines.append(state.final_result)
            
        return "\n".join(lines).strip()
