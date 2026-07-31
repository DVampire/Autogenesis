"""xlsx_reader_tool - read Excel files and return rows as structured data."""

from typing import Any, Dict, Optional
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "Read an Excel workbook and return its rows as structured data."

_INSTRUCTION = """
## Function
Opens an Excel workbook (.xlsx) and returns its rows as structured data (a list of dictionaries, where keys are column headers).

## Guidance
- Use this tool to read data from an Excel file.
- The `path` must be an absolute path.
- By default, it reads the first sheet. You can specify a sheet name using the `sheet` parameter.
- It uses pandas internally to read the file, so ensure pandas and openpyxl are available.

## Parameters
- path (str): Absolute path to the .xlsx file.
- sheet (str, optional): The name of the sheet to read. If not provided, the first sheet is read.

## Example
{"name": "xlsx_reader_tool", "args": {"path": "/abs/path/to/data.xlsx", "sheet": "Sheet1"}}
"""

@TOOL.register_module(force=True)
class XlsxReaderTool(Tool):
    """Read an Excel workbook and return its rows as structured data."""

    name: str = "xlsx_reader_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=True, description="Whether the tool may be evolved (self-optimized)")

    def __init__(self, enable_evolving: bool = True, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, path: str, sheet: Optional[str] = None, **kwargs) -> Response:
        """Read an Excel file and return rows as structured data."""
        try:
            import pandas as pd
            import os

            if not os.path.isabs(path):
                return Response(
                    type=ResponseType.TOOL,
                    success=False,
                    message=f"Error: path must be absolute, got {path}"
                )
                
            if not os.path.exists(path):
                return Response(
                    type=ResponseType.TOOL,
                    success=False,
                    message=f"Error: file not found at {path}"
                )

            # Read the excel file
            if sheet:
                df = pd.read_excel(path, sheet_name=sheet)
            else:
                df = pd.read_excel(path)

            # Fill NaN values with None so they are JSON serializable
            df = df.where(pd.notnull(df), None)

            # Convert to list of dicts
            rows = df.to_dict(orient="records")

            return Response(
                type=ResponseType.TOOL,
                success=True,
                message=f"Successfully read {len(rows)} rows from {path}",
                data={"rows": rows, "path": path, "sheet": sheet}
            )
        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=str(e))
