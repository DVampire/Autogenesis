"""Not Diamond Router."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class NotdiamondTool(PluginTool):
    """Not Diamond Router."""

    name: str = 'notdiamond'
    display_name: str = 'Not Diamond Router'
    description: str = 'Call the right model at the right time with the world'

    async def __call__(self, input_value: str = "", models: str = "", api_key: str = "", **kwargs) -> Response:
        import httpx
        key = self._secret(api_key, "NOTDIAMOND_API_KEY")
        model_list = [m.strip() for m in str(models or "").split(",") if m.strip()]
        if not input_value or not key or not model_list:
            return self._fail("notdiamond: 'input_value', 'models' and api_key are required.")
        try:
            resp = httpx.post("https://api.notdiamond.ai/v2/modelRouter/modelSelect",
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                              json={"messages": [{"role": "user", "content": input_value}],
                                    "llm_providers": [{"provider": m.split("/")[0], "model": m.split("/")[-1]} for m in model_list]},
                              timeout=60.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"notdiamond: {type(exc).__name__}: {exc}")
        return self._ok("Not Diamond selected a model.", selected=data.get("providers"), result=data)
