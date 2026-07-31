"""Science: the workstation half of a project — notebooks, and what runs them."""

from autogenesis.science.server import ScienceManagerServer, base_path, science_manager
from autogenesis.science.types import ComputeStatus, Notebook

__all__ = [
    "ComputeStatus",
    "Notebook",
    "ScienceManagerServer",
    "base_path",
    "science_manager",
]
