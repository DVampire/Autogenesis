"""Pure record-transform processors.

Each accepts records either directly (``records=[...]``) or wrapped in an
upstream capability's ``data`` envelope (``data={"records": [...]}``) — so a
``datasource`` node can feed a ``process`` node with ``${source.data}`` without
the user hand-threading the ``.records`` sub-path.
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import Field

from autogenesis.registry import PROCESS
from autogenesis.response.types import Response, ResponseType
from autogenesis.process.types import Processor


def _coerce_records(records: Any, data: Any) -> List[Dict[str, Any]]:
    """Pull a list of record dicts out of whatever the upstream node handed us.

    Connecting a capability's ``data`` output port yields the whole
    ``{records, count, …}`` envelope, so ``records`` may arrive as that dict —
    unwrap it. Also accepts a JSON-string list or a separate ``data`` envelope.
    """
    records = _as_list(records)
    if isinstance(records, dict) and isinstance(records.get("records"), list):
        return records["records"]
    if isinstance(records, list):
        return records
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"]
    if isinstance(data, list):
        return data
    return []


def _as_list(value: Any) -> Any:
    """Coerce a canvas-compiled arg to a list.

    List/object ports compile to JSON-string args in the workflow language, so a
    ``["a","b"]`` literal arrives as the string ``'["a","b"]'``. Parse it back;
    leave genuine lists and non-JSON strings untouched.
    """
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                return value
    return value


@PROCESS.register_module(force=True)
class SelectFieldsProcessor(Processor):
    """Keep only the named fields on each record (drop the rest)."""

    name: str = "select_fields"
    description: str = "Project each record down to a chosen list of fields."
    instruction: str = (
        "## Function\nKeep only ``fields`` on each record.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- fields (list[str]): field names to keep (required)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None,
                       fields: Optional[List[str]] = None, **kwargs) -> Response:
        rows = _coerce_records(records, data)
        keep = _as_list(fields) or []
        if not isinstance(keep, list) or not keep:
            return Response(type=ResponseType.TOOL, success=False,
                            message="select_fields: 'fields' is required.")
        out = [{k: row.get(k) for k in keep} for row in rows if isinstance(row, dict)]
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Selected {len(keep)} field(s) across {len(out)} record(s).",
                        data={"records": out, "count": len(out)})


@PROCESS.register_module(force=True)
class HeadProcessor(Processor):
    """Take the first ``n`` records."""

    name: str = "head"
    description: str = "Keep only the first n records."
    instruction: str = (
        "## Function\nReturn the first ``n`` records.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- n (int): how many to keep (default 10)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None, n: int = 10, **kwargs) -> Response:
        rows = _coerce_records(records, data)
        try:
            n = max(0, int(n))
        except (TypeError, ValueError):
            n = 10
        out = rows[:n]
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Kept first {len(out)} of {len(rows)} record(s).",
                        data={"records": out, "count": len(out)})


@PROCESS.register_module(force=True)
class RenameFieldsProcessor(Processor):
    """Rename fields on each record via a {old: new} mapping."""

    name: str = "rename_fields"
    description: str = "Rename record fields via a {old: new} mapping."
    instruction: str = (
        "## Function\nRename keys on each record.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- mapping (object): {old_name: new_name} (required)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None,
                       mapping: Any = None, **kwargs) -> Response:
        rows = _coerce_records(records, data)
        mapping = _as_list(mapping)
        if not isinstance(mapping, dict) or not mapping:
            return Response(type=ResponseType.TOOL, success=False,
                            message="rename_fields: 'mapping' object is required.")
        out = [{mapping.get(k, k): v for k, v in row.items()} for row in rows if isinstance(row, dict)]
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Renamed {len(mapping)} field(s) across {len(out)} record(s).",
                        data={"records": out, "count": len(out)})


_OPS = {
    "eq": lambda a, b: a == b, "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b, "ge": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b, "le": lambda a, b: a is not None and a <= b,
}


@PROCESS.register_module(force=True)
class FilterRowsProcessor(Processor):
    """Keep records whose field satisfies a comparison."""

    name: str = "filter_rows"
    description: str = "Keep records where field <op> value (eq/ne/gt/ge/lt/le)."
    instruction: str = (
        "## Function\nKeep rows where ``field`` compares to ``value``.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- field (str): field to test (required).\n- op (str): eq/ne/gt/ge/lt/le (default eq).\n"
        "- value: comparison value (numbers are compared numerically)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None,
                       field: str = "", op: str = "eq", value: Any = None, **kwargs) -> Response:
        rows = _coerce_records(records, data)
        if not field:
            return Response(type=ResponseType.TOOL, success=False, message="filter_rows: 'field' is required.")
        compare = _OPS.get(str(op or "eq"))
        if compare is None:
            return Response(type=ResponseType.TOOL, success=False, message=f"filter_rows: unknown op '{op}'.")
        # Numeric-coerce the comparison value when the string looks like a number.
        if isinstance(value, str):
            try:
                value = float(value) if ("." in value or "e" in value.lower()) else int(value)
            except (TypeError, ValueError):
                pass
        out = [row for row in rows if isinstance(row, dict) and compare(row.get(field), value)]
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Kept {len(out)} of {len(rows)} record(s) where {field} {op} {value}.",
                        data={"records": out, "count": len(out)})


@PROCESS.register_module(force=True)
class DeriveReturnProcessor(Processor):
    """Add a period-over-period return column derived from a price field."""

    name: str = "derive_return"
    description: str = "Add a 'return' column = (x - prev_x) / prev_x over a price field."
    instruction: str = (
        "## Function\nAppend a simple return column from consecutive ``field`` values.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows (assumed time-ordered).\n"
        "- field (str): price field (default ``close``).\n- output (str): new column name (default ``return``)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None,
                       field: str = "close", output: str = "return", **kwargs) -> Response:
        rows = _coerce_records(records, data)
        out: List[Dict[str, Any]] = []
        prev = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            current = row.get(field)
            ret = None
            if isinstance(current, (int, float)) and isinstance(prev, (int, float)) and prev != 0:
                ret = (current - prev) / prev
            out.append({**row, output: ret})
            if isinstance(current, (int, float)):
                prev = current
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Derived '{output}' from '{field}' over {len(out)} record(s).",
                        data={"records": out, "count": len(out)})


@PROCESS.register_module(force=True)
class ToEvalRecordsProcessor(Processor):
    """Shape records into the {task_id, prediction, ground_truth} eval format.

    The bridge from a data pipeline to a ``benchmark`` node: pick which fields
    carry the prediction and the ground truth (and optionally an id).
    """

    name: str = "to_eval_records"
    description: str = "Map fields to {task_id, prediction, ground_truth} for a benchmark node."
    instruction: str = (
        "## Function\nReshape rows for evaluation.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- prediction_field (str): field holding the prediction (default ``prediction``).\n"
        "- ground_truth_field (str): field holding the truth (default ``ground_truth``).\n"
        "- id_field (str): optional field for task_id (else the row index)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None,
                       prediction_field: str = "prediction", ground_truth_field: str = "ground_truth",
                       id_field: str = "", **kwargs) -> Response:
        rows = _coerce_records(records, data)
        out: List[Dict[str, Any]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            task_id = row.get(id_field) if id_field else None
            out.append({
                "task_id": str(task_id) if task_id is not None else str(index),
                "prediction": row.get(prediction_field),
                "ground_truth": row.get(ground_truth_field),
            })
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Shaped {len(out)} record(s) for evaluation.",
                        data={"records": out, "count": len(out)})


@PROCESS.register_module(force=True)
class SortRecordsProcessor(Processor):
    """Sort records by a field."""

    name: str = "sort_records"
    description: str = "Sort records ascending/descending by a field."
    instruction: str = (
        "## Function\nSort records by ``key``.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- key (str): field to sort by (required).\n- descending (bool): default false."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None,
                       key: str = "", descending: bool = False, **kwargs) -> Response:
        rows = _coerce_records(records, data)
        if not key:
            return Response(type=ResponseType.TOOL, success=False,
                            message="sort_records: 'key' is required.")
        out = sorted(
            [row for row in rows if isinstance(row, dict)],
            key=lambda row: (row.get(key) is None, row.get(key)),
            reverse=bool(descending),
        )
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"Sorted {len(out)} record(s) by '{key}'"
                                f"{' desc' if descending else ' asc'}.",
                        data={"records": out, "count": len(out)})
