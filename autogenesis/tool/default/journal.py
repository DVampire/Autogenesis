"""Journal tool — read/write the evolution journal (hypothesis → prediction → attribution).

Pairs with the generate/optimize/evaluate triplet: the optimizer records a
hypothesis BEFORE evolving a component; the evaluator backfills the actual
gating outcome AFTER the next benchmark/reviewer pass. The optimizer reads the
journal first so it never re-proposes a hypothesis that was already reverted.

Backed by ``src/extension/journal.py``; stores ``extension/.journal/<module>/<name>.md``.
"""

from typing import Any, Dict

from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.logger import logger
from autogenesis.registry import TOOL

_DESCRIPTION = "Read/write the evolution journal: record a hypothesis, backfill its outcome, or review prior rounds."

_INSTRUCTION = """
## Function
Maintain the per-component evolution memory so evolution is hypothesis-driven and does not repeat failed ideas.

## Actions (pass `action`)
- `show`: render prior rounds for a component (predicted vs actually-flipped, reverted list). Args: `module`, `name`.
- `record`: log a new hypothesis for this round BEFORE evolving. Args: `module`, `name`, `hypothesis_id`, `lever` (configuration|control|action|instruction), `predicted_flip` (list of task_ids), `note`.
- `gate`: backfill the actual outcome AFTER evaluation. Args: `module`, `name`, `outcome` (accepted|reverted|noop), `attribution` (dict task_id -> bool flipped), optional `round_no`.
- `reverted`: list hypothesis_ids already reverted (never re-propose these). Args: `module`, `name`.

`module` is one of: tool | agent | prompt | skill | environment | connector.

## Guidance
- Optimizer: call `show` + `reverted` first; then `record` your hypothesis; then evolve.
- Evaluator/reviewer: after the next eval, call `gate` to attribute predicted vs actual flips.

## Example
{"name": "journal_tool", "args": {"action": "record", "module": "tool", "name": "calculator_tool", "hypothesis_id": "h3", "lever": "instruction", "predicted_flip": ["task_17"], "note": "trim tool instruction to cut parse errors"}}
"""


@TOOL.register_module(force=True)
class JournalTool(Tool):
    """Record/attribute evolution hypotheses (the evolution-memory lever)."""

    name: str = "journal_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Writes the evolution journal under extension/.journal/.")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, action: str = "show", **kwargs) -> Response:
        from autogenesis.extension.journal import journal
        action = (action or "show").lower().strip()
        try:
            if action == "show":
                module, name = kwargs["module"], kwargs["name"]
                return Response(type=ResponseType.TOOL, success=True,
                                message=journal.render_context(module, name),
                                data={"rounds": [r.model_dump() for r in journal.read(module, name)]})

            if action == "record":
                module, name = kwargs["module"], kwargs["name"]
                rnd = journal.append_round(
                    module, name,
                    hypothesis_id=kwargs["hypothesis_id"],
                    lever=kwargs.get("lever", "instruction"),
                    predicted_flip=kwargs.get("predicted_flip") or [],
                    note=kwargs.get("note", ""),
                )
                return Response(type=ResponseType.TOOL, success=True,
                                message=f"Recorded round {rnd.round} hypothesis '{rnd.hypothesis_id}' for {module}:{name}.",
                                data=rnd.model_dump())

            if action == "gate":
                module, name = kwargs["module"], kwargs["name"]
                rnd = journal.fill_gating(
                    module, name,
                    outcome=kwargs["outcome"],
                    attribution=kwargs.get("attribution") or {},
                    round_no=kwargs.get("round_no"),
                )
                if rnd is None:
                    return Response(type=ResponseType.TOOL, success=False,
                                    message=f"No round to gate for {module}:{name}.")
                return Response(type=ResponseType.TOOL, success=True,
                                message=f"Gated round {rnd.round} of {module}:{name} as '{rnd.gating_outcome}'.",
                                data=rnd.model_dump())

            if action == "reverted":
                module, name = kwargs["module"], kwargs["name"]
                rev = journal.reverted_hypotheses(module, name)
                return Response(type=ResponseType.TOOL, success=True,
                                message=f"Reverted hypotheses for {module}:{name}: {rev}",
                                data={"reverted": rev})

            return Response(type=ResponseType.TOOL, success=False,
                            message=f"Unknown action {action!r}. Use show | record | gate | reverted.")
        except KeyError as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Missing required arg: {e}")
        except Exception as e:
            logger.error(f"| ❌ journal_tool {action} failed: {e}")
            return Response(type=ResponseType.TOOL, success=False, message=f"Error: {e}")
