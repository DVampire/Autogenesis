"""List Home Assistant States."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class HomeassistantListHomeAssistantStatesTool(PluginTool):
    """List Home Assistant States."""

    name: str = 'list_home_assistant_states'
    display_name: str = 'List Home Assistant States'
    description: str = ''

    async def __call__(self, ha_url: str = "", ha_token: str = "", filter_domain: str = "", **kwargs) -> Response:
        import httpx
        token = self._secret(ha_token, "HA_TOKEN", "HOMEASSISTANT_TOKEN")
        if not ha_url or not token:
            return self._fail("homeassistant: 'ha_url' and token (HA_TOKEN) are required.")
        try:
            resp = httpx.get(f"{ha_url.rstrip('/')}/api/states",
                             headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, timeout=30.0)
            resp.raise_for_status()
            states = resp.json()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"homeassistant: {type(exc).__name__}: {exc}")
        if filter_domain:
            states = [s for s in states if str(s.get("entity_id", "")).startswith(f"{filter_domain}.")]
        return self._ok(f"Home Assistant has {len(states)} states.", records=states, count=len(states))
