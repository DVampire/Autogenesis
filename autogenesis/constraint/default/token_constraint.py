"""TokenConstraint — limits cumulative LLM token consumption per task."""

from typing import Any, Dict

from pydantic import Field

from autogenesis.constraint.types import Constraint, ConstraintContext, ConstraintStatus
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import CONSTRAINT


@CONSTRAINT.register_module()
class TokenConstraint(Constraint):
    """Stops the agent when total LLM tokens consumed in this task exceeds the cap.

    Each call adds ``input["token"]`` to the cumulative count. The cap may be
    overridden per call via ``input["max_token"]``.
    """

    name: str = Field(default="token_constraint")
    description: str = Field(default="Stops the agent when total LLM tokens consumed in this task exceeds the cap.")
    max_token: int = Field(default=10_000_000, description="Default maximum cumulative tokens allowed.")

    async def __call__(self, input: Dict[str, Any], ctx: ConstraintContext) -> Response:
        max_token = self._effective_limit(ctx.id, input, "max_token", self.max_token)
        state = self._state[ctx.id]
        state["token"] = state.get("token", 0) + input.get("token", 0)
        token = state["token"]

        data = {
            "status": ConstraintStatus(
                name=self.name,
                used=token,
                limit=max_token,
                unit="tokens",
            ).model_dump(),
        }
        if token >= max_token:
            return Response(
                type=ResponseType.CONSTRAINT,
                success=False,
                message=f"Token limit reached ({token:,}/{max_token:,})",
                data=data,
            )
        return Response(type=ResponseType.CONSTRAINT,
                        success=True,
                        message=f"Current token [{token:,}/{max_token:,}] within limit.",
                        data=data
                        )
