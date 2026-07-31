"""Run MonitorAgent standalone on a long-running bash command.

The agent starts the command in a subprocess and polls it every
``poll_interval`` seconds, logging progress until the process exits.

Usage
-----
# Default demo: sleeps 90 s (three 30-s poll cycles), then prints done
python examples/run_monitor_agent.py

# Custom command
python examples/run_monitor_agent.py --command "bash my_long_job.sh"

# Faster polling for quick tests
python examples/run_monitor_agent.py \\
    --command "for i in 1 2 3 4 5; do echo step \$i; sleep 4; done" \\
    --cfg-options monitor_agent.poll_interval=5 monitor_agent.max_wait=60
"""

import asyncio
import json
import os
import sys
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
from autogenesis.task import task_manager, TaskCategory, TaskPriority, TaskRecord, TaskStatus
from autogenesis.trace import trace_manager
from autogenesis.session.types import SessionContext
from autogenesis.utils import make_id


_DEFAULT_COMMAND = (
    "for i in $(seq 1 9); do "
    "echo \"[step $i] working...\"; "
    "sleep 10; "
    "done; "
    "echo 'done'"
)


def parse_args():
    parser = argparse.ArgumentParser(description="Run MonitorAgent on a long-running bash command")
    parser.add_argument(
        "--config",
        default=os.path.join(root, "configs", "monitor_agent.py"),
        help="Config file path",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="Bash command to run (default: 90-second demo loop)",
    )
    parser.add_argument(
        "--cfg-options",
        nargs="+",
        action=DictAction,
        help="Override config options in key=value format",
    )
    return parser.parse_args()


async def run_monitor(record: TaskRecord, ctx: SessionContext):
    """TaskManager handler: runs MonitorAgent for one TaskRecord."""
    command = (record.task.metadata or {}).get("command") or record.task.content

    response = await agent_manager(
        name="monitor_agent",
        input={
            "task": record.task.content,
            "command": command,
        },
        ctx=ctx,
    )
    return response


async def main():
    args = parse_args()

    config.initialize(config_path=args.config, args=args)
    logger.initialize(config=config)
    logger.info(f"| Config: {config.pretty_text}")

    logger.info("| 📁 Initializing version manager...")
    await version_manager.initialize()

    await trace_manager.initialize()
    await trace_manager.start()

    await hook_manager.initialize()

    logger.info("| 🧠 Initializing model manager...")
    await model_manager.initialize()

    logger.info("| 📁 Initializing prompt manager...")
    await prompt_manager.initialize()

    logger.info("| 📁 Initializing memory manager...")
    memory_names = getattr(config, "memory_names", [])
    await memory_manager.initialize(memory_names=memory_names)

    logger.info("| 🛠️  Initializing tools...")
    tool_names = getattr(config, "tool_names", [])
    await tool_manager.initialize(tool_names=tool_names)

    logger.info("| 🎯 Initializing skills...")
    skill_names = getattr(config, "skill_names", None)
    await skill_manager.initialize(skill_names=skill_names)

    logger.info("| 🔌 Initializing connectors...")
    connector_names = getattr(config, "connector_names", None)
    await connector_manager.initialize(connector_names=connector_names)
    logger.info(f"| ✅ Connectors: {await connector_manager.list()}")

    logger.info("| 🤖 Initializing agents...")
    await agent_manager.initialize(agent_names=config.agent_names)
    logger.info(f"| ✅ Agents: {await agent_manager.list()}")

    # --- Session & TaskManager ---
    session_id = make_id()
    ctx = SessionContext(id=session_id, name="run_monitor_agent")

    task_log_root = os.path.join(config.log_root, "tasks")
    await task_manager.initialize(
        workspace_root=task_log_root,
        handler=lambda record: run_monitor(record, ctx),
    )
    await task_manager.start(num_workers=1)

    # --- Submit ---
    command = args.command or _DEFAULT_COMMAND
    task_text = f"Monitor the following command: {command}"

    logger.info(f"| 📋 Submitting task")
    logger.info(f"|    Command: {command}")

    task_id = await task_manager.submit(
        content=task_text,
        category=TaskCategory.USER,
        priority=TaskPriority.HIGH,
        metadata={"command": command},
    )
    logger.info(f"| ✅ Task submitted: {task_id}")

    # --- Wait for completion ---
    while True:
        record = await task_manager.get(task_id)
        if record and record.task.status in (
            TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED
        ):
            break
        await asyncio.sleep(2)

    record = await task_manager.get(task_id)
    if record.task.status == TaskStatus.DONE:
        logger.info(f"| ✅ Task completed: {task_id}")
        if record.result:
            logger.info(f"| 📄 Result (last 1000 chars):\n{str(record.result)[-1000:]}")
    else:
        logger.error(
            f"| ❌ Task ended with status {record.task.status}: {record.error}"
        )

    # --- Teardown ---
    await task_manager.stop()
    await trace_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
