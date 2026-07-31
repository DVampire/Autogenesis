"""Generic text / JSON processors — the Langflow-style transform toolbox.

Unlike ``records.py`` (record/column ops), these are general transforms over
text and JSON: split, regex, parse, type-convert, combine, extract. Every one is
pure and returns the canonical ``{message, data, files}`` envelope.
"""

import json
import re
from typing import Any, Dict, List, Optional

from pydantic import Field

from autogenesis.registry import PROCESS
from autogenesis.response.types import Response, ResponseType
from autogenesis.process.types import Processor
from autogenesis.process.default.records import _coerce_records


def _as_text(value: Any) -> str:
    """Coerce an upstream arg to text — accepts a str, or a {message}/{data} envelope."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("message"), str):
            return value["message"]
        return json.dumps(value, ensure_ascii=False)
    return str(value)


@PROCESS.register_module(force=True)
class SplitTextProcessor(Processor):
    """Split a text into chunks by separator or fixed size."""

    name: str = "split_text"
    description: str = "Split text into chunks by a separator or a fixed length."
    instruction: str = (
        "## Function\nSplit ``text`` into chunks.\n\n"
        "## Parameters\n- text (str): input text (or an upstream message).\n"
        "- separator (str): split on this (e.g. ``\\n\\n``); default splits on newlines.\n"
        "- chunk_size (int): if >0 and no separator, split into fixed-size chunks."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, text: Any = None, separator: str = "", chunk_size: int = 0, **kwargs) -> Response:
        source = _as_text(text)
        if separator:
            chunks = source.split(separator.encode().decode("unicode_escape"))
        elif chunk_size and int(chunk_size) > 0:
            size = int(chunk_size)
            chunks = [source[i:i + size] for i in range(0, len(source), size)]
        else:
            chunks = source.splitlines()
        chunks = [chunk for chunk in chunks if chunk != ""]
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Split into {len(chunks)} chunk(s).",
                        data={"chunks": chunks, "records": [{"text": chunk} for chunk in chunks], "count": len(chunks)})


@PROCESS.register_module(force=True)
class RegexExtractProcessor(Processor):
    """Extract regex matches from text."""

    name: str = "regex_extract"
    description: str = "Extract all matches of a regex pattern from text."
    instruction: str = (
        "## Function\nReturn every match of ``pattern`` in ``text``.\n\n"
        "## Parameters\n- text (str): input text.\n- pattern (str): a regex (required).\n"
        "- group (int): capture group to return (default 0 = whole match)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, text: Any = None, pattern: str = "", group: int = 0, **kwargs) -> Response:
        if not pattern:
            return Response(type=ResponseType.TOOL, success=False, message="regex_extract: 'pattern' is required.")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            return Response(type=ResponseType.TOOL, success=False, message=f"regex_extract: bad pattern: {exc}")
        try:
            group = int(group)
        except (TypeError, ValueError):
            group = 0
        matches = [match.group(group) if match.groups() or group == 0 else match.group(0)
                   for match in compiled.finditer(_as_text(text))]
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Found {len(matches)} match(es).",
                        data={"matches": matches, "records": [{"match": m} for m in matches], "count": len(matches)})


@PROCESS.register_module(force=True)
class ParseJsonProcessor(Processor):
    """Parse a JSON string into structured data."""

    name: str = "parse_json"
    description: str = "Parse a JSON string into structured data (object or records)."
    instruction: str = (
        "## Function\nParse ``text`` as JSON.\n\n"
        "## Parameters\n- text (str): a JSON string (or an upstream message)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, text: Any = None, **kwargs) -> Response:
        raw = _as_text(text).strip()
        try:
            value = json.loads(raw)
        except (ValueError, TypeError) as exc:
            return Response(type=ResponseType.TOOL, success=False, message=f"parse_json: invalid JSON: {exc}")
        records = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        return Response(type=ResponseType.TOOL, success=True, message="Parsed JSON.",
                        data={"value": value, "records": records, "count": len(records)})


@PROCESS.register_module(force=True)
class TypeConvertProcessor(Processor):
    """Convert a value to another primitive type."""

    name: str = "type_convert"
    description: str = "Convert a value to string / int / float / bool / json."
    instruction: str = (
        "## Function\nConvert ``value`` to type ``to``.\n\n"
        "## Parameters\n- value: the input value.\n- to (str): string/int/float/bool/json (default string)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, value: Any = None, to: str = "string", **kwargs) -> Response:  # noqa: A002
        target = str(to or "string").lower()
        try:
            if target in ("str", "string", "text"):
                result: Any = _as_text(value) if not isinstance(value, str) else value
            elif target in ("int", "integer"):
                result = int(float(value))
            elif target in ("float", "number"):
                result = float(value)
            elif target in ("bool", "boolean"):
                result = str(value).strip().lower() in ("1", "true", "yes", "y", "on")
            elif target == "json":
                result = json.loads(value) if isinstance(value, str) else value
            else:
                return Response(type=ResponseType.TOOL, success=False, message=f"type_convert: unknown type '{to}'.")
        except (TypeError, ValueError) as exc:
            return Response(type=ResponseType.TOOL, success=False, message=f"type_convert: {exc}")
        return Response(type=ResponseType.TOOL, success=True, message=f"Converted to {target}.",
                        data={"value": result})


@PROCESS.register_module(force=True)
class CombineTextProcessor(Processor):
    """Join records' text (or a list of texts) into one string."""

    name: str = "combine_text"
    description: str = "Join a field across records (or a text list) into one string."
    instruction: str = (
        "## Function\nJoin values into a single text.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- field (str): which field to join (default ``text``).\n- separator (str): default newline."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None,
                       field: str = "text", separator: str = "\n", **kwargs) -> Response:
        rows = _coerce_records(records, data)
        sep = (separator or "\n").encode().decode("unicode_escape")
        parts = [str(row.get(field)) for row in rows if isinstance(row, dict) and row.get(field) is not None]
        joined = sep.join(parts)
        return Response(type=ResponseType.TOOL, success=True,
                        message=joined if joined else f"Combined 0 of {len(rows)} record(s).",
                        data={"text": joined, "count": len(parts)})


@PROCESS.register_module(force=True)
class ExtractFieldProcessor(Processor):
    """Pull one field's values out of records into a flat list."""

    name: str = "extract_field"
    description: str = "Extract a single field's values from records into a list."
    instruction: str = (
        "## Function\nCollect ``field`` from every record.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- field (str): the field to extract (required)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None, field: str = "", **kwargs) -> Response:
        if not field:
            return Response(type=ResponseType.TOOL, success=False, message="extract_field: 'field' is required.")
        rows = _coerce_records(records, data)
        values = [row.get(field) for row in rows if isinstance(row, dict) and field in row]
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Extracted '{field}' from {len(values)} record(s).",
                        data={"values": values, "records": [{field: v} for v in values], "count": len(values)})
