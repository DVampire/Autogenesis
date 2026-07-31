"""Redis Chat Memory."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import MemoryPluginTool


class RedisChatTool(MemoryPluginTool):
    """Redis Chat Memory."""

    name: str = 'redis_chat'
    display_name: str = 'Redis Chat Memory'
    description: str = 'Retrieves and store chat messages from Redis.'
    category: str = 'agent'
    type: str = 'memory'

    def _history(self, session_id: str, **cfg: Any) -> Any:
        from langchain_community.chat_message_histories import RedisChatMessageHistory
        return RedisChatMessageHistory(session_id=session_id,
                                       url=cfg.get("redis_url") or "redis://localhost:6379")

    async def __call__(self, action: str = "get", session_id: str = "default", message: str = "",
                       role: str = "user", redis_url: str = "redis://localhost:6379", **kwargs) -> Response:
        return await self._memory(action=action, session_id=session_id, message=message, role=role,
                                  **{k: v for k, v in kwargs.items()})
