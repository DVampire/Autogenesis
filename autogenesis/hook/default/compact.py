"""CompactHook — generic summariser.

Compresses a list of records into a single short text. Used by the memory
systems to consolidate overflow ``recent_history`` into ``working_memory``,
but deliberately knows nothing about TraceEvents or memory internals: callers
pass pre-formatted text lines, the hook returns a summary.

Contract
--------
input:
    event:            required (any HookEvent; callers use ON_CALL)
    items:            list[str]  — records to compress
    existing_summary: str        — optional prior summary, to avoid repetition
    instruction:      str        — optional summary instruction
    model_name:       str        — optional model override
output:
    HookResult(output=<summary text>)
"""

from __future__ import annotations

from autogenesis.registry import HOOK
from autogenesis.logger import logger
from autogenesis.message import SystemMessage, HumanMessage
from autogenesis.model import model_manager
from autogenesis.hook.types import HookContext, HookResult, Hook


_SYSTEM_PROMPT = "You are a concise summariser for an AI agent's execution history."

_DEFAULT_INSTRUCTION = (
    "Summarise the records above in 2-4 sentences. Focus on what agents ran, "
    "what tools/skills were called, key results, and any failures. Preserve exact "
    "values (file paths, numbers, errors). Do not repeat the existing summary."
)


@HOOK.register_module(force=True)
class CompactHook(Hook):
    name: str = "compact"
    description: str = "Generic summariser: compress a list of records into a short text."
    priority: int = 50

    model_name: str = ""

    async def handle(self, ctx: HookContext) -> HookResult:
        """Summarise the supplied ``items`` into a single short text via the LLM.

        Builds a prompt from the records (optionally appending any prior summary
        and a custom instruction) and asks the model for a concise consolidation.
        Model errors are swallowed so the caller always gets a well-formed result.

        Args:
            ctx: Hook context whose ``input`` may carry ``items`` (records to
                compress), ``existing_summary``, ``instruction`` and ``model_name``.

        Returns:
            ``HookResult`` whose ``output`` holds the summary text, or ``None``
            when there is nothing to summarise or the model call fails.
        """
        inp = ctx.input or {}
        items = inp.get("items") or []
        if not items:
            return HookResult.allow()

        existing = inp.get("existing_summary") or ""
        model = inp.get("model_name") or self.model_name
        instruction = inp.get("instruction") or _DEFAULT_INSTRUCTION

        prior = f"Existing summary:\n{existing}\n\n" if existing else ""
        body = "\n".join(f"- {it}" for it in items)
        prompt = f"{prior}New records:\n{body}\n\n{instruction}"

        try:
            response = await model_manager(
                name=model,
                input={
                    "messages": [
                        SystemMessage(content=_SYSTEM_PROMPT),
                        HumanMessage(content=prompt),
                    ],
                },
            )
            text = response.message.strip() if response.success else ""
            logger.debug(f"| 🗜️ CompactHook: {len(items)} records → {len(text)} chars")
        except Exception as e:
            logger.warning(f"| ⚠️ CompactHook failed: {e}")
            text = ""

        return HookResult(output=text or None)
