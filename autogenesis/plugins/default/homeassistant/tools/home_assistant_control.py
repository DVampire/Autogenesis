"""Home Assistant Control."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class HomeassistantHomeAssistantControlTool(PluginTool):
    """Home Assistant Control."""

    name: str = 'home_assistant_control'
    display_name: str = 'Home Assistant Control'
    description: str = ''

    async def __call__(self, ha_url: str = "", ha_token: str = "", domain: str = "", service: str = "", entity_id: str = "", **kwargs) -> Response:
        import httpx
        token = self._secret(ha_token, "HA_TOKEN", "HOMEASSISTANT_TOKEN")
        if not ha_url or not token or not domain or not service:
            return self._fail("homeassistant.control: needs ha_url, token, domain, service.")
        try:
            resp = httpx.post(f"{ha_url.rstrip('/')}/api/services/{domain}/{service}",
                              headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                              json={"entity_id": entity_id} if entity_id else {}, timeout=30.0)
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"homeassistant.control: {type(exc).__name__}: {exc}")
        return self._ok(f"Called {domain}.{service}.", result=result)
