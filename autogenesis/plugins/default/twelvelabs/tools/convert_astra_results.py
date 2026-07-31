"""Convert Astra DB to Pegasus Input."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class TwelvelabsConvertAstraResultsTool(PluginTool):
    """Convert Astra DB to Pegasus Input."""

    name: str = 'convert_astra_results'
    display_name: str = 'Convert Astra DB to Pegasus Input'
    description: str = 'Converts Astra DB search results to inputs compatible with TwelveLabs Pegasus.'

    async def __call__(self, results: Optional[list] = None, **kwargs) -> Response:
        rows = results or []
        records = [{"content": str(r)} for r in rows]
        return self._ok(f"Converted {len(records)} Astra results.", records=records, count=len(records))
