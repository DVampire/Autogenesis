"""Table (DataFrame) operations — Langflow's dataframe_operations equivalent.

One ``table_operations`` processor dispatches a chosen pandas operation over the
incoming records: head / tail / sort / drop_duplicates / select / drop columns /
group_by / describe. Records in, records out, so it composes with every other
node. Pure (no side effects).
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import Field

from autogenesis.registry import PROCESS
from autogenesis.response.types import Response, ResponseType
from autogenesis.process.types import Processor
from autogenesis.process.default.records import _as_list, _coerce_records

_OPERATIONS = ["head", "tail", "sort", "drop_duplicates", "select_columns", "drop_columns", "group_by", "describe"]


def _to_records(dataframe) -> List[Dict[str, Any]]:
    """DataFrame → JSON-safe records (NaN → null via the json round-trip)."""
    return json.loads(dataframe.to_json(orient="records"))


@PROCESS.register_module(force=True)
class TableOperationsProcessor(Processor):
    """Run a pandas DataFrame operation over records."""

    name: str = "table_operations"
    description: str = "DataFrame ops over records: head/tail/sort/drop_duplicates/select/drop/group_by/describe."
    instruction: str = (
        "## Function\nRun one DataFrame ``operation`` over the incoming records.\n\n"
        "## Parameters\n- records (list) OR data ({records}): input rows.\n"
        "- operation (str): head/tail/sort/drop_duplicates/select_columns/drop_columns/group_by/describe.\n"
        "- n (int): row count for head/tail (default 5).\n"
        "- column (str): sort key / group_by aggregated column.\n"
        "- columns (list): for select_columns/drop_columns/drop_duplicates subset.\n"
        "- ascending (bool): sort order (default true).\n"
        "- by (str): group_by key.\n- agg (str): count/sum/mean/min/max (group_by, default count)."
    )
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"canvas_category": "process"})

    async def __call__(self, records: Any = None, data: Any = None, operation: str = "head",
                       n: int = 5, column: str = "", columns: Any = None,
                       ascending: bool = True, by: str = "", agg: str = "count", **kwargs) -> Response:
        import pandas as pd

        rows = _coerce_records(records, data)
        operation = str(operation or "head").lower()
        if operation not in _OPERATIONS:
            return Response(type=ResponseType.TOOL, success=False,
                            message=f"table_operations: unknown operation '{operation}'.")
        frame = pd.DataFrame(rows)
        cols = [str(c) for c in (_as_list(columns) or [])] if columns else []
        try:
            n = max(0, int(n))
        except (TypeError, ValueError):
            n = 5

        try:
            if operation == "head":
                out = frame.head(n)
            elif operation == "tail":
                out = frame.tail(n)
            elif operation == "sort":
                if not column:
                    return Response(type=ResponseType.TOOL, success=False, message="table_operations: sort needs 'column'.")
                out = frame.sort_values(by=column, ascending=bool(ascending))
            elif operation == "drop_duplicates":
                out = frame.drop_duplicates(subset=cols or None)
            elif operation == "select_columns":
                out = frame[cols] if cols else frame
            elif operation == "drop_columns":
                out = frame.drop(columns=[c for c in cols if c in frame.columns], errors="ignore")
            elif operation == "group_by":
                if not by:
                    return Response(type=ResponseType.TOOL, success=False, message="table_operations: group_by needs 'by'.")
                grouped = frame.groupby(by)
                target = frame[[by] + ([column] if column and column in frame.columns else [])]
                func = str(agg or "count").lower()
                out = getattr(target.groupby(by), func)().reset_index() if hasattr(target.groupby(by), func) \
                    else grouped.size().reset_index(name="count")
            else:  # describe
                out = frame.describe(include="all").reset_index()
        except Exception as exc:  # noqa: BLE001 — a bad op/arg is a failed result
            return Response(type=ResponseType.TOOL, success=False, message=f"table_operations: {exc}")

        result = _to_records(out)
        return Response(type=ResponseType.TOOL, success=True,
                        message=f"{operation}: {len(result)} record(s).",
                        data={"records": result, "count": len(result)})
