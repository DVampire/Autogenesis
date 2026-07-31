"""Canonical path resolution for Autogenesis's writable and bundled resources."""

import os
from pathlib import Path


_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACKAGE_ROOT.parent


def package_root() -> Path:
    """The installed package directory, containing shipped read-only resources."""
    return _PACKAGE_ROOT


def home_dir() -> Path:
    """Machine-level runtime state. Delegates to the path manager.

    Kept as a thin alias because callers outside the framework still import it;
    the layout itself is owned by ``autogenesis.paths`` so there is one table
    describing the tree, not two.
    """
    from autogenesis.paths import P, path_manager

    return path_manager.get(P.RUNTIME, create=True)


def data_path(rel: str = "") -> str:
    """Resolve an absolute path or a user-data path relative to ``home_dir``."""
    if not rel:
        return str(home_dir())
    path = Path(rel).expanduser()
    return str(path.resolve() if path.is_absolute() else (home_dir() / path).resolve())


def project_path(rel: str = "") -> str:
    """Resolve a runtime path against the project directory the layout hangs off.

    Identical to the current directory in the normal case, and to
    ``$AUTOGENESIS_HOME`` when that is set. Going through the path manager is
    what keeps a config-started run and a gateway-started one in the same tree:
    this used to resolve against ``cwd`` unconditionally, so with
    ``AUTOGENESIS_HOME`` set the gateway wrote to ``$HOME/output`` while a run
    launched from a config file wrote to ``./output``.
    """
    from autogenesis.paths import path_manager

    path = Path(rel).expanduser()
    return str(path.resolve() if path.is_absolute() else (path_manager.project_dir() / path).resolve())


def extension_root() -> Path:
    """Shared project extension repository; sessions stage changes elsewhere.

    A thin alias, like :func:`home_dir`: the layout is owned by
    ``autogenesis.paths`` so there is one answer to "where is extension/",
    not one per caller. This used to resolve against ``cwd`` and ignore
    ``AUTOGENESIS_HOME``, so setting that variable relocated ``output/`` but
    left every shared component behind.
    """
    from autogenesis.paths import P, path_manager

    return path_manager.get(P.EXTENSION, create=True)


def resource_path(rel: str) -> str:
    """Find an overrideable shipped resource: home → source tree → package."""
    path = Path(rel).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    for base in (home_dir(), _REPO_ROOT, _PACKAGE_ROOT):
        candidate = base / path
        if candidate.exists():
            return str(candidate)
    return str((_PACKAGE_ROOT / path).resolve())


def get_extension_root() -> str:
    """Writable directory containing self-evolved extension components."""
    return str(extension_root())


def get_package_root() -> str:
    """The installed package directory — for shipped, read-only resources."""
    return str(package_root())


def assemble_workspace_path(path: str) -> str:
    """Resolve a workspace/runtime path relative to the current project directory.

    Args:
        path: Path string (relative or absolute).

    Returns:
        Absolute path string. Absolute inputs are returned as-is.
    """
    return project_path(path)

def assemble_resource_path(path: str) -> str:
    """Resolve a shipped RESOURCE (e.g. a default config) that the user may override.

    Searches home → repo → package, so a config works both in a source checkout and
    when the package is pip-installed.
    """
    return resource_path(path)
