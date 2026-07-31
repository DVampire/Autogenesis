"""Wire/state models for the Science workstation.

The workstation is not a container. It is the base environment plus a Jupyter
Server per project, so the agent, the Science view's REPL and JupyterLab share
one kernel and one set of variables — see :mod:`autogenesis.kernel`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ComputeStatus(BaseModel):
    """What the workstation is running on, as the Compute panel shows it.

    The base environment's own resources — the whole machine, not a slice of
    it, because that is exactly what the agent and the kernel get.
    """

    model_config = ConfigDict(extra="ignore")

    running: bool = False
    #: True while the kernel is executing, so the panel can say so.
    busy: bool = False
    #: Empty on a host with no NVIDIA card. Not an error: the panel says
    #: "no GPU detected" rather than showing a meter with nothing behind it.
    gpus: List[Dict[str, Any]] = Field(default_factory=list)
    cpu_count: Optional[int] = None
    memory_total_mb: Optional[int] = None
    memory_used_mb: Optional[int] = None
    disk_free_mb: Optional[int] = None
    #: How many cells this project's kernel has run, agent and user together.
    executions: int = 0


class Notebook(BaseModel):
    """One ``.ipynb`` in the project's workspace.

    Kept as a real notebook file rather than a private format so the same
    document opens in the embedded JupyterLab, in the Code view's editor, and in
    anything the user later runs over the workspace.
    """

    model_config = ConfigDict(extra="ignore")

    #: Path relative to the workspace root, e.g. ``notebooks/analysis.ipynb``.
    path: str
    title: str = ""
    size_bytes: int = 0
    modified_at: str = ""
    cell_count: int = 0


__all__ = ["ComputeStatus", "Notebook"]
