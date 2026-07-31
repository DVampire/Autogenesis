"""Zep Chat Memory."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import MemoryPluginTool


class ZepTool(MemoryPluginTool):
    """Zep Chat Memory."""

    name: str = 'zep'
    display_name: str = 'Zep Chat Memory'
    description: str = 'Retrieves and store chat messages from Zep.'

    def _history(self, session_id: str, **cfg: Any) -> Any:
        from langchain_community.chat_message_histories import ZepChatMessageHistory
        return ZepChatMessageHistory(session_id=session_id, url=cfg.get("zep_url") or "",
                                     api_key=self._secret(cfg.get("api_key"), "ZEP_API_KEY"))

    async def __call__(self, action: str = "get", session_id: str = "default", message: str = "",
                       role: str = "user", zep_url: str = "", api_key: str = "", **kwargs) -> Response:
        return await self._memory(action=action, session_id=session_id, message=message, role=role,
                                  **{k: v for k, v in kwargs.items()})
