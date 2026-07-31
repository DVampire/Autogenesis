"""Type definitions for the kernel module.

A **kernel** is a live interpreter that outlives the call that used it, so a
later call sees the variables an earlier one defined. One per project: the
kernel is a *resource*, shared like the project's files, not per conversation
and not per run — keying it off ``ctx.id`` meant a fresh interpreter for every
line of dialogue.

Everything that runs code in a project goes through the same kernel: the
agent's ``code_interpreter_tool``, the Science view's REPL, and JupyterLab.
That is the point. There is one set of variables, so there is nothing to keep
in sync — a variable the agent defined is a variable you can print.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

#: Output kinds a cell can produce, in Jupyter's vocabulary.
OutputType = Literal["stream", "result", "display", "error"]

#: MIME types worth carrying back. Everything else in a display bundle is a
#: fallback representation of one of these.
RICH_MIME = ("image/png", "image/jpeg", "image/svg+xml", "text/html", "text/markdown",
             "application/json", "text/latex")


class KernelOutput(BaseModel):
    """One thing a cell produced.

    Images are the reason this is not just a string. ``matplotlib`` returns its
    figure as a ``display_data`` message carrying ``image/png``; a pipeline that
    keeps only ``text/plain`` turns every plot into
    ``<Figure size 640x480 with 1 Axes>``.
    """

    model_config = ConfigDict(extra="ignore")

    type: OutputType
    #: For ``stream``: stdout or stderr. Otherwise unset.
    name: Optional[str] = None
    #: MIME bundle for result/display; ``{"text/plain": ...}`` for a stream.
    data: Dict[str, Any] = Field(default_factory=dict)

    def text(self) -> str:
        """The plain-text rendering, for the transcript and the model's eyes."""
        if self.type == "error":
            return self.data.get("text/plain", "")
        return str(self.data.get("text/plain", ""))

    @property
    def mimes(self) -> List[str]:
        return [mime for mime in self.data if mime != "text/plain"]


class KernelResult(BaseModel):
    """Everything one execution produced."""

    model_config = ConfigDict(extra="ignore")

    success: bool = True
    #: In execution order, so a transcript can replay prints and plots as they came.
    outputs: List[KernelOutput] = Field(default_factory=list)
    error: Optional[str] = None
    #: The kernel's own counter — what Jupyter shows as ``In [n]``.
    execution_count: Optional[int] = None

    def stdout(self) -> str:
        return "".join(o.text() for o in self.outputs if o.type == "stream" and o.name == "stdout")

    def stderr(self) -> str:
        return "".join(o.text() for o in self.outputs if o.type == "stream" and o.name == "stderr")

    def rich(self) -> List[KernelOutput]:
        """Outputs carrying something a screen can show but a log cannot."""
        return [o for o in self.outputs if any(m in RICH_MIME for m in o.mimes)]

    def as_message(self) -> str:
        """Human/LLM-readable rendering.

        Rich outputs are named rather than inlined — a base64 PNG helps nobody
        reading a transcript, and the model only needs to know a figure exists.
        """
        parts: List[str] = []
        for output in self.outputs:
            if output.type == "error":
                continue
            body = output.text().rstrip()
            shown = [m for m in output.mimes if m in RICH_MIME]
            if shown:
                parts.append(f"[{', '.join(shown)}]" + (f" {body}" if body else ""))
            elif body:
                parts.append(body)
        if self.error:
            parts.append(self.error.rstrip())
        return "\n".join(parts) or ("" if self.success else "Execution failed.")


class Execution(BaseModel):
    """One entry in a kernel's history: what was run, and what came back.

    The history is what the Science view renders as a notebook. It is not a
    document anyone edits — it is the kernel's own record, which is why nothing
    has to be synchronised: the agent running a cell and you running one both
    append here, because both went through the same kernel.
    """

    model_config = ConfigDict(extra="ignore")

    #: The kernel's counter, so the UI can label a cell ``[3]`` the way Jupyter does.
    execution_count: Optional[int] = None
    code: str = ""
    language: str = "python"
    outputs: List[KernelOutput] = Field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    #: ``agent`` when a tool call ran it, ``user`` when the REPL did. The panel
    #: shows both — seeing what the agent ran is most of the point.
    origin: Literal["agent", "user"] = "agent"
    started_at: str = ""
    duration_ms: Optional[int] = None


class KernelStatus(BaseModel):
    """What the panel shows next to the prompt."""

    model_config = ConfigDict(extra="ignore")

    running: bool = False
    busy: bool = False
    kernel_name: str = "python3"
    #: How many executions this kernel has served, agent and user together.
    executions: int = 0
    workspace: str = ""


__all__ = ["Execution", "KernelOutput", "KernelResult", "KernelStatus", "OutputType", "RICH_MIME"]
