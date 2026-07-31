from pathlib import Path

import pytest

from autogenesis.config.config import process_general
from autogenesis.paths import P, path_manager
from autogenesis.utils.path_utils import data_path, extension_root, home_dir, project_path
from mmengine import Config as MMConfig


def test_autogenesis_home_relocates_the_whole_tree(monkeypatch, tmp_path: Path) -> None:
    """AUTOGENESIS_HOME moves the tree root — every part of it, not just output/.

    ``extension/`` used to be exempt: it resolved against ``cwd`` in
    ``extension_root()`` while the layout put it under the override, so setting
    this variable relocated generated state and left every shared component
    behind.
    """
    root = tmp_path / "agent-home"
    monkeypatch.setenv("AUTOGENESIS_HOME", str(root))
    monkeypatch.delenv("AUTOGENESIS_EXTENSION_ROOT", raising=False)

    assert home_dir() == (root / "output" / ".runtime").resolve()
    assert Path(data_path("run")).is_relative_to(root.resolve())
    assert extension_root() == (root / "extension").resolve()
    assert Path(project_path("output/demo")) == (root / "output" / "demo").resolve()


def test_extension_root_override_moves_only_that_root(monkeypatch, tmp_path: Path) -> None:
    """AUTOGENESIS_EXTENSION_ROOT relocates shared components, nothing else."""
    home, shared = tmp_path / "agent-home", tmp_path / "shared-components"
    monkeypatch.setenv("AUTOGENESIS_HOME", str(home))
    monkeypatch.setenv("AUTOGENESIS_EXTENSION_ROOT", str(shared))

    assert path_manager.get(P.EXTENSION) == shared.resolve()
    assert path_manager.get(P.EXTENSION_MODULE, module="skill") == (shared / "skill").resolve()
    assert extension_root() == shared.resolve()
    # Generated state stays with the tree root.
    assert path_manager.get(P.OUTPUT) == (home / "output").resolve()


def test_every_resolver_agrees_on_where_extension_lives(monkeypatch, tmp_path: Path) -> None:
    """Skill, connector, config and the layout must answer this identically.

    Each of them used to resolve ``extension/`` itself — against ``cwd``, or an
    env var, or ``project_path`` — so under a relocated tree they disagreed and
    components were written to a directory nothing else read.
    """
    monkeypatch.setenv("AUTOGENESIS_HOME", str(tmp_path))
    monkeypatch.delenv("AUTOGENESIS_EXTENSION_ROOT", raising=False)
    expected = (tmp_path / "extension").resolve()

    from autogenesis.connector.context import ConnectorContextManager
    from autogenesis.skill.context import SkillContextManager

    assert extension_root() == expected
    assert Path(SkillContextManager().extension_skills_dir) == expected / "skill"
    assert Path(ConnectorContextManager().extension_connectors_dir) == expected / "connector"
    config = process_general(MMConfig(dict(
        project_root="output/demo", workspace_root="output/demo/workspace",
        log_root="output/demo/log", log_path="agent.log")))
    assert Path(config.extension_root) == expected


def test_every_declared_path_stays_inside_the_two_roots(monkeypatch, tmp_path: Path) -> None:
    """The layout table is the disk contract — nothing may escape output/ or extension/.

    Asserted rather than left to convention: a third location is exactly how
    .autogenesis/ appeared, root-owned and outside the chown loop that hands
    output/ back to the host user.
    """
    monkeypatch.setenv("AUTOGENESIS_HOME", str(tmp_path))
    monkeypatch.delenv("AUTOGENESIS_EXTENSION_ROOT", raising=False)
    output, extension = path_manager.writable_roots()
    sample = {"owner": "someone", "session_id": "sid", "run_id": "rid",
              "project_key": "key", "module": "skill", "conversation_id": "cid"}

    for key in P:
        resolved = path_manager.get(key, **{p: sample[p] for p in path_manager.params_for(key)})
        assert resolved.is_relative_to(output) or resolved.is_relative_to(extension), (
            f"{key.value} -> {resolved} escapes both writable roots"
        )


def test_missing_placeholder_is_rejected_rather_than_written_literally(monkeypatch, tmp_path: Path) -> None:
    """A forgotten parameter must fail loudly, not create a dir named '{session_id}'."""
    monkeypatch.setenv("AUTOGENESIS_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="session_id"):
        path_manager.get(P.SESSION_WORKSPACE, owner="local")


def test_runtime_output_is_relative_to_the_current_project(monkeypatch, tmp_path: Path) -> None:
    """With no override, everything hangs off the directory the run started in."""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.delenv("AUTOGENESIS_HOME", raising=False)
    monkeypatch.delenv("AUTOGENESIS_EXTENSION_ROOT", raising=False)

    config = process_general(MMConfig(dict(
        project_root="output/demo",
        workspace_root="output/demo/workspace",
        log_root="output/demo/log",
        log_path="agent.log",
    )))

    assert Path(project_path("output/demo")) == project / "output" / "demo"
    assert Path(config.project_root) == project / "output" / "demo"
    assert Path(config.extension_root) == project / "extension"
    assert Path(config.project_root) == path_manager.get(P.OUTPUT) / "demo"
    assert not Path(config.workspace_root).exists()
    assert not Path(config.log_root).exists()
