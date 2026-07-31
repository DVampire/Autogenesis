"""Every capability result normalizes to the same {message, data, files} shape.

This is the backend contract the canvas type system builds on: a step's output
looks the same regardless of which capability produced it, so ${step.data.x}
references resolve uniformly.
"""

from __future__ import annotations

import pytest

from autogenesis.environment.types import ActionResult
from autogenesis.response.types import Response, ResponseType
from autogenesis.workflow.runtime import workflow_runtime


def test_actionresult_exposes_capability_output_contract() -> None:
    result = ActionResult(success=True, message="clicked", extra={"url": "https://x"})
    # data aliases extra; files is part of the shared contract.
    assert result.data == {"url": "https://x"}
    assert result.files is None


def test_response_and_actionresult_normalize_identically() -> None:
    response = Response(type=ResponseType.TOOL, success=True, message="ok",
                        data={"exit_code": 0}, files=["/a"])
    action = ActionResult(success=True, message="clicked", extra={"url": "https://x"})

    normalized_response = workflow_runtime._normalize(response)
    normalized_action = workflow_runtime._normalize(action)

    assert set(normalized_response) == set(normalized_action) == {"message", "data", "files"}
    assert normalized_response == {"message": "ok", "data": {"exit_code": 0}, "files": ["/a"]}
    assert normalized_action == {"message": "clicked", "data": {"url": "https://x"}, "files": None}


def test_failed_capability_results_raise() -> None:
    for failed in (
        Response(type=ResponseType.TOOL, success=False, message="tool boom"),
        ActionResult(success=False, message="env boom"),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            workflow_runtime._normalize(failed)


def test_plain_values_pass_through() -> None:
    assert workflow_runtime._normalize("just text") == "just text"
    assert workflow_runtime._normalize(["a", "b"]) == ["a", "b"]
    assert workflow_runtime._normalize({"k": 1}) == {"k": 1}
