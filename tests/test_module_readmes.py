"""Keep module documentation discoverable and machine-readable."""

from pathlib import Path
import re

import yaml


PACKAGE_ROOT = Path(__file__).parents[1] / "autogenesis"
PLUGIN_ROOT = PACKAGE_ROOT / "plugins" / "default"
REQUIRED_FRONTMATTER = {
    "name", "description", "version", "type", "category", "requirements", "metadata",
}
#: What a generated PLUGIN.md must declare. ``metadata`` is deliberately absent:
#: a plugin manifest carries concrete facts (tools, credentials) rather than a
#: free-form bag.
REQUIRED_PLUGIN_FRONTMATTER = {
    "id", "name", "category", "type", "tools", "implemented", "credentials",
    "requirements", "version",
}


def _frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path} must start with YAML frontmatter"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict), f"{path} frontmatter must be a mapping"
    return data, text[match.end():]


def _is_plugin_package(path: Path) -> bool:
    """A plugin package (or its ``tools/``) documents itself with PLUGIN.md."""
    return path == PLUGIN_ROOT or PLUGIN_ROOT in path.parents


def test_every_managed_python_module_has_a_readme():
    """Bundled Office Skill scripts are resources, not framework modules."""
    module_dirs = [PACKAGE_ROOT]
    for init_file in PACKAGE_ROOT.rglob("__init__.py"):
        directory = init_file.parent
        relative = directory.relative_to(PACKAGE_ROOT)
        if "skill" in relative.parts and "scripts" in relative.parts:
            continue
        if _is_plugin_package(directory):
            continue
        module_dirs.append(directory)

    missing = [str(path.relative_to(PACKAGE_ROOT)) for path in module_dirs
               if not (path / "README.md").is_file()]
    assert not missing, f"Modules missing README.md: {missing}"


def test_all_package_readmes_have_versioned_frontmatter():
    for readme in PACKAGE_ROOT.rglob("README.md"):
        frontmatter, body = _frontmatter(readme)
        assert REQUIRED_FRONTMATTER <= frontmatter.keys(), readme
        assert re.fullmatch(r"\d+\.\d+\.\d+", str(frontmatter["version"])), readme
        assert all(frontmatter[key] for key in ("name", "description", "type", "category")), readme
        assert isinstance(frontmatter["requirements"], list), readme
        assert isinstance(frontmatter["metadata"], dict), readme
        assert re.search(r"(?im)^#\s+\S", body), f"{readme} needs a human-readable title"

        assert str(frontmatter["version"]) == "1.0.0", readme


def test_every_plugin_package_has_a_manifest():
    packages = sorted(path for path in PLUGIN_ROOT.iterdir()
                      if path.is_dir() and (path / "__init__.py").is_file())
    assert packages, "no plugin packages found"

    missing = [path.name for path in packages if not (path / "PLUGIN.md").is_file()]
    assert not missing, f"Plugin packages missing PLUGIN.md: {missing}"

    for package in packages:
        manifest = package / "PLUGIN.md"
        frontmatter, body = _frontmatter(manifest)
        assert REQUIRED_PLUGIN_FRONTMATTER <= frontmatter.keys(), manifest
        assert frontmatter["id"] == package.name, manifest
        assert re.fullmatch(r"\d+\.\d+\.\d+", str(frontmatter["version"])), manifest
        assert isinstance(frontmatter["credentials"], list), manifest
        assert isinstance(frontmatter["requirements"], list), manifest
        assert re.search(r"(?im)^#\s+\S", body), f"{manifest} needs a human-readable title"


def test_plugin_manifests_match_the_code():
    """A manifest that drifts from its package is worse than none at all."""
    from autogenesis.plugins import plugin_manager  # noqa: PLC0415 — import cost
    import asyncio

    async def infos():
        await plugin_manager.initialize()
        try:
            return {config.name: (len(config.tools),
                                  sum(1 for tool in config.tools.values() if tool.implemented))
                    for config in await plugin_manager.list_infos()}
        finally:
            await plugin_manager.cleanup()

    live = asyncio.run(infos())
    mismatches = []
    for package in sorted(PLUGIN_ROOT.iterdir()):
        manifest = package / "PLUGIN.md"
        if not manifest.is_file():
            continue
        frontmatter, _ = _frontmatter(manifest)
        declared = (frontmatter["tools"], frontmatter["implemented"])
        actual = live.get(package.name)
        if actual is None:
            mismatches.append(f"{package.name}: has a manifest but does not register")
        elif declared != actual:
            mismatches.append(f"{package.name}: manifest says {declared}, code has {actual}")
    assert not mismatches, "PLUGIN.md is stale — regenerate it:\n  " + "\n  ".join(mismatches)
