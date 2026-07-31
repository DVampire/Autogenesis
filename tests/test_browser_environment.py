"""Simple integration test for BrowserEnvironment.

Usage:
    # Local Playwright (headless)
    python tests/test_browser_environment.py

    # OpenSandbox Chrome (auto-starts opensandbox-server)
    USE_SANDBOX=1 python tests/test_browser_environment.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

USE_SANDBOX = os.getenv("USE_SANDBOX", "0") == "1"


async def main():
    from autogenesis.config import config
    from autogenesis.environment.server import environment_manager

    # Inject browser environment config before initialize()
    if USE_SANDBOX:
        print("🟡 Mode: OpenSandbox Chrome")
        config["browser_environment"] = {
            "base_dir": "tests/browser_output",
            "use_sandbox": True,
            "sandbox_domain": os.getenv("SANDBOX_DOMAIN", "localhost:8080"),
            "sandbox_api_key": os.getenv("SANDBOX_API_KEY"),
        }
    else:
        print("🟢 Mode: Local Playwright (headless)")
        config["browser_environment"] = {
            "base_dir": "tests/browser_output",
            "headless": True,
        }

    # initialize() auto-discovers and builds all registered environments
    await environment_manager.initialize()
    env = await environment_manager.get("browser_environment")
    assert env is not None, "BrowserEnvironment not found after initialize()"

    # 1. get_state
    print("\n--- get_state ---")
    state = await env.get_state()
    print(f"URL   : {state['extra']['url']}")
    print(f"Title : {state['extra']['title']}")
    print(f"Tabs  : {state['extra']['tabs']}")
    assert state["extra"]["url"], "Expected a non-empty URL"
    assert state["extra"]["screenshots"], "Expected screenshots in state"

    # 2. click
    print("\n--- click ---")
    result = await env.click(x=512, y=384)
    print(f"success: {result['success']}  message: {result['message']}")
    assert result["success"]

    # 3. type
    print("\n--- type ---")
    result = await env.type_text(text="playwright browser test")
    print(f"success: {result['success']}  message: {result['message']}")
    assert result["success"]

    # 4. keypress
    print("\n--- keypress ---")
    result = await env.keypress(keys=["Enter"])
    print(f"success: {result['success']}  message: {result['message']}")
    assert result["success"]

    # 5. wait
    print("\n--- wait ---")
    result = await env.wait(ms=1500)
    print(f"success: {result['success']}  message: {result['message']}")
    assert result["success"]

    # 6. get_state after search
    print("\n--- get_state (after search) ---")
    state = await env.get_state()
    print(f"URL   : {state['extra']['url']}")
    print(f"Title : {state['extra']['title']}")

    # 7. scroll
    print("\n--- scroll ---")
    result = await env.scroll(x=512, y=400, scroll_x=0, scroll_y=300)
    print(f"success: {result['success']}  message: {result['message']}")
    assert result["success"]

    # 8. move
    print("\n--- move ---")
    result = await env.move(x=200, y=200)
    print(f"success: {result['success']}  message: {result['message']}")
    assert result["success"]

    await environment_manager.cleanup()
    print("\n✅ All checks passed")


if __name__ == "__main__":
    asyncio.run(main())
