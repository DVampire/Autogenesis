from pathlib import Path

import pytest

from autogenesis.sandbox.project import ProjectSandbox
from autogenesis.session import SessionContext
from autogenesis.session.project import ensure_session_sandbox, stage_input_files
from autogenesis.config import config


def test_promote_staged_extension_with_audit_record(tmp_path: Path) -> None:
    shared_extension = tmp_path / "shared-extension"
    sandbox = ProjectSandbox.create(
        tmp_path / "project",
        shared_extension_root=shared_extension,
        package_root=tmp_path / "package",
    )
    staged_tool = sandbox.extension_root / "tool" / "hello_tool.py"
    staged_tool.parent.mkdir(parents=True)
    staged_tool.write_text("def hello():\n    return 'hello'\n", encoding="utf-8")

    validation = sandbox.validate()
    assert validation["file_count"] == 1
    report = sandbox.promote()

    promoted = shared_extension / "tool" / "hello_tool.py"
    assert promoted.read_text(encoding="utf-8") == staged_tool.read_text(encoding="utf-8")
    assert report["promoted"][0]["destination"] == str(promoted)
    assert sandbox.manifest_path.exists()


def test_promote_refuses_overwrite_without_opt_in(tmp_path: Path) -> None:
    shared_extension = tmp_path / "shared-extension"
    sandbox = ProjectSandbox.create(tmp_path / "project", shared_extension_root=shared_extension)
    staged_tool = sandbox.extension_root / "tool" / "hello_tool.py"
    staged_tool.parent.mkdir(parents=True)
    staged_tool.write_text("VALUE = 'staged'\n", encoding="utf-8")
    target = shared_extension / "tool" / "hello_tool.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 'shared'\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        sandbox.promote()

    report = sandbox.promote(overwrite=True)
    assert report["backup_root"] is not None
    assert target.read_text(encoding="utf-8") == "VALUE = 'staged'\n"


def test_promote_can_select_only_the_approved_component(tmp_path: Path) -> None:
    shared_extension = tmp_path / "extension"
    sandbox = ProjectSandbox.create(tmp_path / "session", shared_extension_root=shared_extension)
    approved = sandbox.extension_root / "tool" / "approved.py"
    unapproved = sandbox.extension_root / "tool" / "unapproved.py"
    approved.parent.mkdir(parents=True)
    approved.write_text("VALUE = 'approved'\n", encoding="utf-8")
    unapproved.write_text("VALUE = 'unapproved'\n", encoding="utf-8")

    report = sandbox.promote(relative_paths=["tool/approved.py"])

    assert [item["relative_path"] for item in report["components"]] == ["tool/approved.py"]
    assert (shared_extension / "tool" / "approved.py").exists()
    assert not (shared_extension / "tool" / "unapproved.py").exists()


def test_promotion_can_be_rolled_back_after_registration_failure(tmp_path: Path) -> None:
    shared_extension = tmp_path / "extension"
    target = shared_extension / "tool" / "sample.py"
    target.parent.mkdir(parents=True)
    target.write_text("OLD = True\n", encoding="utf-8")
    sandbox = ProjectSandbox.create(tmp_path / "session", shared_extension_root=shared_extension)
    staged = sandbox.extension_root / "tool" / "sample.py"
    staged.parent.mkdir(parents=True)
    staged.write_text("NEW = True\n", encoding="utf-8")

    report = sandbox.promote(overwrite=True)
    assert target.read_text(encoding="utf-8") == "NEW = True\n"
    sandbox.rollback_promotion(report)
    assert target.read_text(encoding="utf-8") == "OLD = True\n"
    audit = sandbox._load_manifest()["promotions"][-1]
    assert audit["status"] == "rolled_back"


def test_direct_context_receives_a_session_sandbox(tmp_path: Path) -> None:
    context = SessionContext(id="direct-run", name="example")

    sandbox = ensure_session_sandbox(
        context,
        tmp_path / "output" / "meta_agent",
        shared_extension_root=tmp_path / "extension",
    )

    assert sandbox is not None
    assert context.extra["workspace_root"] == str(tmp_path / "output" / "meta_agent" / "direct-run" / "workspace")
    assert context.extra["extension_root"] == str(tmp_path / "output" / "meta_agent" / "direct-run" / "extension")
    assert context.extra["shared_extension_root"] == str(tmp_path / "extension")


def test_external_task_file_is_staged_inside_workspace(tmp_path: Path) -> None:
    source = tmp_path / "task.html"
    source.write_text("<h1>task</h1>", encoding="utf-8")
    context = SessionContext(id="direct-run")
    ensure_session_sandbox(context, tmp_path / "output")
    # stage_input_files reads the working dir from config (set per-run by
    # bind_session_roots); mirror that here.
    config.workspace_root = context.extra["workspace_root"]

    prepared = stage_input_files(context, {"task": "review", "files": [str(source)]})

    staged = Path(prepared["files"][0])
    assert staged.is_relative_to(Path(context.extra["workspace_root"]))
    assert staged.read_text(encoding="utf-8") == "<h1>task</h1>"
