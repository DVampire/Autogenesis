import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(verbose=True)

from mmengine import DictAction

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
from autogenesis.agent import agent_manager
from autogenesis.hook import hook_manager
from autogenesis.task import task_manager, TaskCategory, TaskPriority, TaskRecord, TaskStatus, add_task_args, resolve_task
from autogenesis.trace import trace_manager
from autogenesis.session.types import SessionContext
from autogenesis.utils import make_id


def parse_args():
    parser = argparse.ArgumentParser(description="Run GeneralAgent on a task")
    parser.add_argument(
        "--config",
        default=os.path.join(root, "configs", "general_agent.py"),
        help="Config file path",
    )
    add_task_args(parser, default_task_file=os.path.join(root, "examples", "tasks", "arithmetic_steps.html"))
    parser.add_argument(
        "--cfg-options",
        nargs="+",
        action=DictAction,
        help="Override config options in key=value format",
    )
    return parser.parse_args()


async def run_agent(record: TaskRecord):
    """TaskManager handler: executes the general agent for a given TaskRecord."""
    session_id = record.task.session_id or make_id()
    ctx = SessionContext(id=session_id)

    response = await agent_manager(
        name="general_agent",
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
    logger.initialize(config=config)
    logger.info(f"| Config: {config.pretty_text}")

    # --- Core managers ---
    logger.info("| 📁 Initializing version manager...")
    await version_manager.initialize()
    logger.info(f"| ✅ Versions: {await version_manager.list()}")

    # --- Trace ---
    trace_log_root = os.path.join(config.log_root, "trace")
    await trace_manager.initialize(log_root=trace_log_root)
    await trace_manager.start()

    # --- Hooks --- (registers all default hooks: trace_hook + memory_hook)
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

    logger.info("| 🛠️ Initializing tools...")
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

    logger.info("| 🤖 Initializing agents...")
    await agent_manager.initialize(agent_names=config.agent_names)
    logger.info(f"| ✅ Agents: {await agent_manager.list()}")

    logger.info(f"| 📋 All versions: {json.dumps(await version_manager.list(), indent=4)}")

    # --- TaskManager ---
    task_log_root = os.path.join(config.log_root, "tasks")
    await task_manager.initialize(log_root=task_log_root, handler=run_agent)
    await task_manager.start(num_workers=1)

    # --- Submit task (inline --task or --task-file document) ---
    task_text, task_files, task_metadata = resolve_task(
        args, task_log_root,
        default_text="What is the result of 23 multiplied by 47? Please calculate it step by step.",
    )
    logger.info(f"| 📋 Submitting task: {task_text}")
    task_id = await task_manager.submit(
        content=task_text,
        category=TaskCategory.USER,
        priority=TaskPriority.HIGH,
        files=task_files,
        metadata=task_metadata,
    )
    logger.info(f"| ✅ Task submitted: {task_id}")

    # --- Wait for completion ---
    while True:
        record = await task_manager.get(task_id)
        if record and record.task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            break
        await asyncio.sleep(1)

    record = await task_manager.get(task_id)
    if record.task.status == TaskStatus.DONE:
        logger.info(f"| ✅ Task completed: {task_id}")
    else:
        logger.error(f"| ❌ Task ended with status {record.task.status}: {record.error}")

    # --- Teardown ---
    await task_manager.stop()
    await trace_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
