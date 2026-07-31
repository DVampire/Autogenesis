import sys
import asyncio
import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(verbose=True)

root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.version import version_manager
from autogenesis.prompt import prompt_manager
from autogenesis.utils import count_tokens

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_get_messages():
    config.initialize(config_path="configs/base.py", args=__import__("argparse").Namespace())
    logger.initialize(config=config)
    await version_manager.initialize()
    await prompt_manager.initialize()

    prompt_name = "reason_act_agent"
    system_modules = {
        "max_actions": 5,
        "workspace_root": "/tmp/workspace_root",
    }
    agent_modules = {
        "agent_context": "agent examples",
        "tool_context": "tool examples",
        "skill_context": "skill examples",
        "examples": "example tokens"
    }

    messages = await prompt_manager.get_messages(
        prompt_name=prompt_name,
        system_modules=system_modules,
        agent_modules=agent_modules,
    )

    assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"

    system_msg, user_msg = messages

    print("System Message:")
    print(system_msg)
    print(f"System Message Tokens: {count_tokens(system_msg.text)}")
    print()

    print("\nUser Message:")
    print(user_msg)
    print(f"User Message Tokens: {count_tokens(user_msg.text)}")

    logger.info("| ✅ test_get_messages passed")


if __name__ == "__main__":
    asyncio.run(test_get_messages())
