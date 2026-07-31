"""Place Call."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class OlivyaTool(PluginTool):
    """Place Call."""

    name: str = 'olivya'
    display_name: str = 'Place Call'
    description: str = 'A component to create an outbound call request from Olivya'

    async def __call__(self, from_number: str = "", to_number: str = "", first_message: str = "", system_prompt: str = "", api_key: str = "", **kwargs) -> Response:
        import httpx
        key = self._secret(api_key, "OLIVYA_API_KEY")
        if not from_number or not to_number or not key:
            return self._fail("olivya: 'from_number', 'to_number' and api_key (OLIVYA_API_KEY) are required.")
        payload = {"variables": {"first_message": first_message or None, "system_prompt": system_prompt or None},
                   "from_number": from_number.strip(), "to_number": to_number.strip()}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://phone.olivya.io/create_zap_call",
                                         headers={"Authorization": key, "Content-Type": "application/json"},
                                         json=payload, timeout=30.0)
                resp.raise_for_status()
                result = resp.json()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"olivya: {type(exc).__name__}: {exc}")
        return self._ok("Olivya call created.", result=result)
