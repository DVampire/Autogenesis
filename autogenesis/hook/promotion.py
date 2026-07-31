"""Promotion bridge used after a registration hook has accepted a staged component."""

from pathlib import Path

from autogenesis.sandbox.project import ProjectSandbox
from autogenesis.utils import get_extension_root


def promote_approved_component(extension_root: str, component_path: str) -> str:
    """Validate and promote exactly one approved staged extension component.

    The session staging root is never used as a durable extension directory.
    """
    staged_root = Path(extension_root).expanduser().resolve()
    component = Path(component_path).expanduser().resolve()
    try:
        relative = component.relative_to(staged_root)
    except ValueError as exc:
        raise ValueError(f"Component is outside staged extension root: {component}") from exc
    sandbox = ProjectSandbox.create(
        staged_root.parent,
        shared_extension_root=get_extension_root(),
    )
    if sandbox.extension_root != staged_root:
        raise ValueError(f"Invalid staged extension root: {extension_root}")
    report = sandbox.promote(overwrite=True, relative_paths=[str(relative)])
    if len(report["promoted"]) != 1:
        raise ValueError("Expected exactly one promoted extension component")
    return report["promoted"][0]["destination"]
