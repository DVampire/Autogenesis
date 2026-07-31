"""Run a framework control command from the CLI.

The human front-end onto the command layer (the others are MetaAgent's control_tool and
orchestration code). Boots the managers a command needs, then dispatches one `/command`
and prints the result. Commands are synchronous control operations, so this does NOT go
through the task queue.

Examples:
    python examples/run_command.py /help
    python examples/run_command.py /registry
    python examples/run_command.py /checkpoint pre-evolve
    python examples/run_command.py /rollback tool bash_tool 1.0.0
"""
import os
import sys
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
from autogenesis.version import version_manager
from autogenesis.prompt import prompt_manager
from autogenesis.tool import tool_manager
from autogenesis.skill import skill_manager
from autogenesis.connector import connector_manager
from autogenesis.environment import environment_manager
from autogenesis.agent import agent_manager
from autogenesis.command import command_manager


def parse_args():
    parser = argparse.ArgumentParser(description="Run a framework control command")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="The command line, e.g. /registry or /rollback tool bash_tool 1.0.0")
    parser.add_argument("--config", default=os.path.join(root, "configs", "code_agent.py"),
                        help="Config file (determines which capabilities are registered).")
    parser.add_argument("--cfg-options", nargs="+", action=DictAction,
                        help="Override config options in key=value format")
    return parser.parse_args()


async def main():
    args = parse_args()
    if not args.command:
        print("usage: python examples/run_command.py /<command> [args]   (try /help)")
        return

    config.initialize(config_path=args.config, args=args)
    logger.initialize(config=config)

    # Boot the managers a control command may touch. version_manager backs
    # /registry, /versions, /checkpoint; the capability managers back /rollback;
    # agent_manager backs /evolve.
    await version_manager.initialize()
    await prompt_manager.initialize()
    await tool_manager.initialize(tool_names=getattr(config, "tool_names", None))
    await skill_manager.initialize(skill_names=getattr(config, "skill_names", None))
    await connector_manager.initialize(connector_names=getattr(config, "connector_names", None))
    await environment_manager.initialize(env_names=getattr(config, "environment_names", None))
    await agent_manager.initialize(agent_names=getattr(config, "agent_names", None))
    await command_manager.initialize()

    raw = " ".join(args.command)
    resp = await command_manager.dispatch(raw)

    print("\n" + ("✅" if resp.success else "❌") + f" {raw}")
    print(resp.message)


if __name__ == "__main__":
    asyncio.run(main())
