"""Integration test for R support in the code_interpreter sandbox.

Requires a reachable Docker daemon + the project's conda env (has opensandbox /
opensandbox-server / code_interpreter installed — on this machine that's the
`agentos` env, see scripts/INSTALL.md) and the docker/code-interpreter image
built locally:

    docker build -t autogenesis/code-interpreter:latest docker/code-interpreter

Usage:
    conda activate agentos  # or whichever env has opensandbox installed
    python tests/test_r_sandbox.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))


async def main():
    from autogenesis.sandbox import sandbox_manager
    from autogenesis.tool.default.code_interpreter import CodeInterpreterTool

    # 1. Directly through the sandbox handle.
    print("--- sandbox_manager.acquire('code_interpreter') + run_code(language='r') ---")
    sandbox = await sandbox_manager.acquire("code_interpreter", reuse_key="test_r_sandbox")
    result = await sandbox.run_code("cat(R.version.string, '\\n')", language="r")
    print(result.as_message())
    assert result.success, f"R execution failed: {result.error or result.stderr}"
    assert "R version" in result.stdout

    # 2. Through the LLM-facing tool (mirrors how an agent would call it).
    print("\n--- code_interpreter_tool(language='r') ---")
    tool = CodeInterpreterTool()
    resp = await tool(code="x <- 6 * 7\ncat(x, '\\n')", language="r", ctx=_Ctx("test_r_sandbox"))
    print(resp.message)
    assert resp.success
    assert "42" in resp.message

    # 3. Regression check: python still goes through the persistent kernel.
    print("\n--- code_interpreter_tool(language='python') regression check ---")
    resp = await tool(code="print(2 + 2)", language="python", ctx=_Ctx("test_r_sandbox"))
    print(resp.message)
    assert resp.success
    assert "4" in resp.message

    await sandbox_manager.cleanup()
    print("\n✅ All checks passed")


class _Ctx:
    def __init__(self, id: str):
        self.id = id


if __name__ == "__main__":
    asyncio.run(main())
