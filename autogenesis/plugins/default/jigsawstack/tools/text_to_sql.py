"""Text to SQL."""

from autogenesis.response.types import Response
from autogenesis.plugins.default.jigsawstack._base import JigsawstackToolBase


class JigsawstackTextToSqlTool(JigsawstackToolBase):
    """Text to SQL."""

    name: str = 'text_to_sql'
    display_name: str = 'Text to SQL'
    description: str = 'Convert natural language to SQL queries using JigsawStack AI'

    async def __call__(self, prompt: str = "", sql_schema: str = "", api_key: str = "", **kwargs) -> Response:
        params = {"prompt": prompt, "sql_schema": sql_schema}
        return await self._run("text_to_sql", {k: v for k, v in params.items() if v not in (None, "", [])}, api_key)
