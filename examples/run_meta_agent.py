"""Run MetaAgent with code_agent and general_agent as sub-agents.

Usage
-----
# Default task
python examples/run_meta_agent.py

# Custom task
python examples/run_meta_agent.py --task "Write a Python function to reverse a string and add unit tests."

# Override config options
python examples/run_meta_agent.py --task "..." --cfg-options model_name=openai/o3
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(verbose=True)

from mmengine import DictAction
import argparse

root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.model import model_manager
from autogenesis.version import version_manager
from autogenesis.prompt import prompt_manager
from autogenesis.memory import memory_manager
from autogenesis.tool import tool_manager
from autogenesis.skill import skill_manager
from autogenesis.connector import connector_manager
from autogenesis.environment import environment_manager
from autogenesis.agent import agent_manager
from autogenesis.extension import extension_manager
from autogenesis.hook import hook_manager
from autogenesis.task import task_manager, TaskCategory, TaskPriority, TaskRecord, TaskStatus, add_task_args, resolve_task
from autogenesis.trace import trace_manager
from autogenesis.trajectory import trajectory_manager
from autogenesis.session.types import SessionContext
from autogenesis.session.project import ensure_session_sandbox, bind_session_roots
from autogenesis.utils import make_id


def parse_args():
    parser = argparse.ArgumentParser(description="Run MetaAgent on a task")
    parser.add_argument(
        "--config",
        default=os.path.join(root, "configs", "meta_agent.py"),
        help="Config file path",
    )
    add_task_args(parser, default_task_file=os.path.join(root, "examples", "tasks", "calculator_tool.html"))
    parser.add_argument(
        "--cfg-options",
        nargs="+",
        action=DictAction,
        help="Override config options in key=value format",
    )
    return parser.parse_args()


async def run_agent(record: TaskRecord, ctx: SessionContext):

    response = await agent_manager(
        name="meta_agent",
        input={
            "task": record.task.content,
            "files": record.task.files,
        },
        ctx=ctx,
    )
    return response


async def main():
    args = parse_args()

    config.initialize(config_path=args.config, args=args)
    # A direct script is a session too: bind all runtime state before managers
    # initialize, so no tag-level log/workspace directories are created.
    session_id = make_id()
    ctx = SessionContext(id=session_id, name="main_entrypoint")
    # Same directory the gateway would use for this session — see autogenesis/paths.
    sandbox = ensure_session_sandbox(
        ctx,
        shared_extension_root=config.extension_root,
    )
    bind_session_roots(config, sandbox)
    extension_manager.set_base_dir(config.extension_root)
    logger.initialize(config=config)
    logger.info(f"| Config: {config.pretty_text}")

    # Validate the assembled config (duplicate whitelist entries silently shadow).
    from autogenesis.config import validate_assembly
    for _problem in validate_assembly(config):
        logger.warning(f"| ⚠️ Config: {_problem}")

    # --- Core managers ---
    logger.info("| 📁 Initializing version manager...")
    await version_manager.initialize()
    logger.info(f"| ✅ Versions: {await version_manager.list()}")

    # --- Trace ---
    await trace_manager.initialize()
    await trace_manager.start()

    # --- Trajectory (training-data capture; fed by trajectory_hook) ---
    await trajectory_manager.initialize()

    # --- Hooks ---
    await hook_manager.initialize()

    logger.info("| 🧠 Initializing model manager...")
    await model_manager.initialize()
    logger.info(f"| ✅ Models: {model_manager.list()}")

    logger.info("| 📁 Initializing prompt manager...")
    await prompt_manager.initialize()
    logger.info(f"| ✅ Prompts: {await prompt_manager.list()}")

    logger.info("| 📁 Initializing memory manager...")
    await memory_manager.initialize(memory_names=config.memory_names)
    logger.info(f"| ✅ Memory: {await memory_manager.list()}")

    logger.info("| 🛠️  Initializing tools...")
    await tool_manager.initialize(tool_names=config.tool_names)
    logger.info(f"| ✅ Tools: {await tool_manager.list()}")

    logger.info("| 🎯 Initializing skills...")
    skill_names = getattr(config, "skill_names", None)
    await skill_manager.initialize(skill_names=skill_names)
    logger.info(f"| ✅ Skills: {await skill_manager.list()}")

    logger.info("| 🔌 Initializing connectors...")
    connector_names = getattr(config, "connector_names", None)
    await connector_manager.initialize(connector_names=connector_names)
    logger.info(f"| ✅ Connectors: {await connector_manager.list()}")

    logger.info("| 🌐 Initializing environments...")
    env_names = getattr(config, "env_names", None)
    if env_names:
        await environment_manager.initialize(env_names=env_names)
        logger.info(f"| ✅ Environments: {await environment_manager.list()}")

    logger.info("| 🤖 Initializing agents...")
    await agent_manager.initialize(agent_names=config.agent_names)
    logger.info(f"| ✅ Agents: {await agent_manager.list()}")

    # Layer hot-pluggable extensions (external `extension/`) on top of built-ins.
    _ext_manifest = await extension_manager.initialize()
    logger.info(f"| ✅ Extensions loaded: {[f'{c.module}:{c.name}' for c in _ext_manifest.components]}")

    logger.info(f"| 📋 All versions: {json.dumps(await version_manager.list(), indent=4)}")

    # --- TaskManager ---
    task_log_root = os.path.join(config.log_root, "tasks")
    await task_manager.initialize(log_root=task_log_root, handler=lambda record: run_agent(record, ctx))
    await task_manager.start(num_workers=1)

    # --- Build the task (inline --task string or --task-file document) ---
    task_text, task_files, task_metadata = resolve_task(args, task_log_root)
    logger.info(f"| 📋 Submitting task:\n{task_text}")
    task_id = await task_manager.submit(
        content=task_text,
        category=TaskCategory.USER,
        priority=TaskPriority.HIGH,
        files=task_files,
        metadata=task_metadata,
    )
    logger.info(f"| ✅ Session id: {session_id}, Task id: {task_id}")

    # --- Wait for completion ---
    while True:
        record = await task_manager.get(task_id)
        if record and record.task.status in (
            TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED
        ):
            break
        await asyncio.sleep(1)

    record = await task_manager.get(task_id)
    if record.task.status == TaskStatus.DONE:
        logger.info(f"| ✅ Task completed: {task_id}")
        logger.info(f"| 📄 Result:\n{record.result}")
    else:
        logger.error(f"| ❌ Task ended with status {record.task.status}: {record.error}")

    # --- Print memory HTML path if available ---
    # Response.extra / Response.data are Optional[dict]; guard against None.
    if record.result is not None:
        extra = getattr(record.result, "extra", None)
        data = getattr(record.result, "data", None)
        memory_path = None
        for src in (extra, data):
            if isinstance(src, dict) and src.get("memory_path"):
                memory_path = src["memory_path"]
                break
        if memory_path:
            logger.info(f"| 📄 Memory HTML: {memory_path}")

    # --- Teardown ---
    # Clean up environments (browser peer containers) and the sandbox subsystem while
    # the event loop and the opensandbox SDK executor are still alive. Relying on the
    # asyncio-atexit cleanups instead fails at process exit ("Executor shutdown has
    # been called"), leaking peer containers.
    await task_manager.stop()
    try:
        await environment_manager.cleanup()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"| ⚠️ environment cleanup: {e}")
    try:
        from autogenesis.sandbox import sandbox_manager
        await sandbox_manager.cleanup()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"| ⚠️ sandbox cleanup: {e}")
    await trace_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
