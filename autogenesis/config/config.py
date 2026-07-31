import os
from mmengine import Config as MMConfig
from argparse import Namespace
from typing import Union

from autogenesis.utils import assemble_resource_path, assemble_workspace_path, project_path, Singleton

def process_general(config: MMConfig) -> MMConfig:
    """Resolve and validate the per-run output directory hierarchy.

    Only ``project_root`` need be declared by a config; the ``log_root`` and
    ``workspace_root`` sub-roots default to ``<project_root>/log`` and
    ``<project_root>/workspace`` when a config does not set them.  These are just
    templates — a session rebinds them to ``<project_root>/<session-id>/…`` at
    runtime (direct scripts via ``bind_session_roots``; Gateway/CLI via a
    per-session ``ProjectSandbox`` plus ctx-driven log routing).
    """
    if "project_root" not in config:
        raise ValueError("Configuration is missing required output root: project_root")
    # Derive the sub-roots from project_root when a config omits them.
    if "log_root" not in config:
        config.log_root = f"{config.project_root}/log"
    if "workspace_root" not in config:
        config.workspace_root = f"{config.project_root}/workspace"

    # Runtime output is project-owned: these resolve against the project the
    # layout hangs off, so a config-started run lands in the same tree the
    # gateway uses.
    project_root = os.path.realpath(project_path(config.project_root))
    workspace_root = os.path.realpath(project_path(config.workspace_root))
    log_root = os.path.realpath(project_path(config.log_root))
    # Extensions are durable project assets, deliberately kept alongside the
    # project's ``output/`` directory rather than inside one run's output tree.
    # An explicit config value still wins; otherwise the layout decides, so a
    # config-started run and a browser-started one agree on where shared
    # components live.
    from autogenesis.paths import P, path_manager

    configured = config.get("extension_root")
    extension_root = os.path.realpath(
        project_path(configured) if configured else str(path_manager.get(P.EXTENSION)))

    for root_name, root_path in (("workspace_root", workspace_root), ("log_root", log_root)):
        if os.path.commonpath((project_root, root_path)) != project_root:
            raise ValueError(f"{root_name} must be located under project_root: {root_path}")

    config.project_root = project_root
    config.workspace_root = workspace_root
    config.log_root = log_root
    config.extension_root = extension_root
    # Publish the resolved root so the path manager — and therefore every
    # component initialized after configuration — agrees with it. Writing back
    # the layout's own default is a no-op; what this actually propagates is an
    # explicit ``extension_root`` from the config file.
    os.environ["AUTOGENESIS_EXTENSION_ROOT"] = extension_root
    # ``project_root``, ``workspace_root`` and ``log_root`` are templates until a
    # session is bound — creating them here would leave empty tag-level directories
    # beside the real per-session ones (``ProjectSandbox`` creates the whole path it
    # needs). Only the durable extension root is materialized eagerly.
    os.makedirs(extension_root, exist_ok=True)

    log_path = os.path.join(log_root, config.log_path)
    config.log_path = log_path

    return config

def process_tools(config: MMConfig) -> MMConfig:
    for key in config:
        # Skip agent configs (e.g. tool_generate_agent): their key contains "tool"
        # but they are agents — handled by process_agent, not as tools.
        if "tool" in key and not key.endswith("_agent"):
            if "base_dir" in config[key]:
                # Tool state belongs to the run's log root.
                base_dir = str(assemble_workspace_path(os.path.join(config.log_root, config[key]["base_dir"])))
                config[key].update(dict(
                    base_dir = base_dir
                ))
    return config

def process_environments(config: MMConfig) -> MMConfig:
    for key in config:
        # Skip agent configs (e.g. environment_generate_agent): key contains
        # "environment" but they are agents — handled by process_agent.
        if "environment" in key and not key.endswith("_agent"):
            if "base_dir" in config[key]:
                base_dir = str(assemble_workspace_path(os.path.join(config.log_root, config[key]["base_dir"])))
                config[key].update(dict(
                    base_dir = base_dir
                ))
    return config

def process_memory(config: MMConfig)->MMConfig:
    for key in config:
        if "memory" in key:
            if "base_dir" in config[key]:
                base_dir = str(assemble_workspace_path(os.path.join(config.log_root, config[key]["base_dir"])))
                config[key].update(dict(
                    base_dir = base_dir
                ))
            if "model_name" in config[key]:
                model_name = config.model_name
                config[key].update(
                    dict(
                        model_name = model_name
                    )
                )
    return config

def process_agent(config: MMConfig) -> MMConfig:
    for key in config:
        if key != "agent" and not key.endswith("_agent"):
            continue
        entry = config[key]
        if not hasattr(entry, "get"):   # not a config dict (e.g. agent_names list)
            continue
        # An agent's base_dir is its workspace location (never joined onto log_root).
        # Default to the run's workspace root when a config doesn't set one, so configs
        # only declare project_root and the workspace is derived / session-rebound.
        base_dir = entry.get("base_dir") or config.workspace_root
        config[key].update(dict(
            base_dir = str(assemble_workspace_path(base_dir))
        ))
        if entry.get("model_name") is not None:
            config[key].update(dict(
                model_name = config.model_name
            ))
    return config

class Config(MMConfig, metaclass=Singleton):
    def __init__(self):
        super(Config, self).__init__()

    def initialize(self, config_path: Union[str], args: Namespace, verbose: bool = True) -> None:
        # Config files are shipped resources the user may override — resolve them in
        # home → repo → package order so this works both in a checkout and when installed.
        config_path = str(assemble_resource_path(config_path))
        mmconfig = MMConfig.fromfile(filename=config_path)
        if 'cfg_options' not in args or args.cfg_options is None:
            cfg_options = dict()
        else:
            cfg_options = args.cfg_options
        for item in args.__dict__:
            if item not in ['config', 'cfg_options'] and args.__dict__[item] is not None:
                cfg_options[item] = args.__dict__[item]

        mmconfig.merge_from_dict(cfg_options)

        # Process general configuration
        mmconfig = process_general(mmconfig)
        mmconfig = process_tools(mmconfig)
        mmconfig = process_environments(mmconfig)
        mmconfig = process_memory(mmconfig)
        mmconfig = process_agent(mmconfig)
        if verbose:
            print(mmconfig.pretty_text)

        self.__dict__.update(mmconfig.__dict__)

    def dump(self) -> str:
        """Dump the configuration"""
        return super().dump()

config = Config()
# Auto-load the default config at import so `config` is populated for callers that don't
# initialize explicitly. Kept quiet and fault-tolerant: importing the package must not
# crash just because a default config isn't present (an explicit initialize() can follow).
try:
    config.initialize(config_path="configs/base.py", args=Namespace(), verbose=False)
except Exception as _e:  # noqa: BLE001
    import warnings
    warnings.warn(f"autogenesis: default config not loaded at import ({_e}). "
                  f"Call config.initialize(<your_config>) explicitly.", RuntimeWarning)
