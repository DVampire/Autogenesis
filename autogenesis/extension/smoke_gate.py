"""Replay smoke gate — a cheap post-evolution safety net.

Borrowed from HarnessX's "replay门": instead of asserting on an evolved
component, run a *synthetic* task through the real agent run loop and treat any
crash / error exit as a rejection. A newly generated tool/agent/prompt that
imports cleanly but blows up the loop (bad schema, exception on first use,
runaway) is caught here before it is committed to the manifest.

Design:
- ``replay_smoke`` is dependency-injectable via ``probe`` so the decision logic
  is testable without a live model. The default probe drives a probe agent
  through one synthetic step with a cheap model (resolved from a model role).
- Smoke events are emitted with ``provenance=HEALTHCHECK`` so consumers can
  filter them out of live traces.
- On failure the caller rolls back to the previous archived version (evolved
  component) or unloads it (brand-new component) — reusing ExtensionManager's
  existing ``rollback`` / ``unload``. This module only *decides*; it does not
  mutate the manifest itself.

It is enabled by default. Administrative restore/import paths may explicitly pass
``run_smoke=False`` after validating the exact archived artifact.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from autogenesis.logger import logger


class ReplayReport(BaseModel):
    """Outcome of a smoke run."""

    ok: bool
    reason: str = ""
    exit_reason: Optional[str] = None
    module: str = ""
    name: str = ""


class EvolutionRejected(Exception):
    """Raised when a newly evolved component fails the replay smoke gate."""


# A probe returns (ok, reason). Injected in tests; defaults to a real agent run.
Probe = Callable[[str, str, str, float], Awaitable[ReplayReport]]

_SYNTHETIC_TASK = (
    "Synthetic replay smoke check. Do not perform any real work. "
    "Reply by calling done_tool with exactly: OK"
)


async def _default_probe(module: str, name: str, model_role: str, timeout_s: float) -> ReplayReport:
    """Run one synthetic task through the real run loop with a cheap model.

    Uses a general-purpose probe agent so the evolved component's registration
    and the loop wiring are exercised end-to-end. Any crash / error exit / timeout
    is a failure. Kept lazy-import so importing this module never drags in the
    agent/model stack.
    """
    from autogenesis.agent.server import agent_manager
    from autogenesis.model.server import model_manager
    from autogenesis.session.types import SessionContext

    # Resolve a cheap probe model from the role (falls back to main inside model layer).
    probe_model = _resolve_probe_model(model_role)

    # Pick a lightweight built-in probe agent. general_agent is the simplest actor.
    probe_agent_name = "general_agent"
    try:
        agent = await agent_manager.get(probe_agent_name)
    except Exception as e:
        return ReplayReport(ok=False, reason=f"probe agent unavailable: {e}", module=module, name=name)
    if agent is None:
        return ReplayReport(ok=False, reason=f"probe agent '{probe_agent_name}' not registered", module=module, name=name)

    # Bound the run: cheap model + tiny step budget + wall-clock timeout.
    if probe_model:
        try:
            agent = agent.model_copy(update={"model_name": probe_model, "max_step": 2})
        except Exception:
            pass

    ctx = SessionContext(id=f"smoke_{module}_{name}")
    try:
        resp = await asyncio.wait_for(agent(task=_SYNTHETIC_TASK, ctx=ctx), timeout=timeout_s)
    except asyncio.TimeoutError:
        return ReplayReport(ok=False, reason=f"smoke timed out after {timeout_s}s", exit_reason="timeout",
                            module=module, name=name)
    except Exception as e:
        return ReplayReport(ok=False, reason=f"smoke raised: {e}", exit_reason="error", module=module, name=name)

    data = getattr(resp, "data", None) or {}
    ok = bool(getattr(resp, "success", False)) and not data.get("stopped_by_constraint", False)
    return ReplayReport(
        ok=ok,
        reason="" if ok else f"probe run did not succeed (message={getattr(resp, 'message', '')!r})",
        exit_reason="done" if ok else "error",
        module=module,
        name=name,
    )


def _resolve_probe_model(model_role: str) -> Optional[str]:
    """Resolve a model name from a named role via config.model_roles, else None."""
    try:
        from autogenesis.config import config
        roles = getattr(config, "model_roles", None) or {}
        if isinstance(roles, dict):
            return roles.get(model_role) or roles.get("smoke") or roles.get("main")
    except Exception:
        pass
    return None


async def replay_smoke(
    module: str,
    name: str,
    *,
    probe: Optional[Probe] = None,
    model_role: str = "smoke",
    timeout_s: float = 60.0,
) -> ReplayReport:
    """Run the smoke gate for a component. Returns a ReplayReport (never raises)."""
    runner = probe or _default_probe
    try:
        report = await runner(module, name, model_role, timeout_s)
    except Exception as e:  # a broken probe must not crash the evolution path
        report = ReplayReport(ok=False, reason=f"probe error: {e}", exit_reason="error", module=module, name=name)
    if report.ok:
        logger.info(f"| 🩺 Replay smoke passed: {module}:{name}")
    else:
        logger.warning(f"| 🩺 Replay smoke FAILED: {module}:{name} — {report.reason}")
    return report


__all__ = ["ReplayReport", "EvolutionRejected", "replay_smoke"]
