"""Evolution journal — hypothesis → prediction → attribution memory for evolved components.

Borrowed from HarnessX's journal: each evolution round records a *hypothesis*
(what change and why), the *lever* it pulls, which tasks it *predicts* will flip
fail→pass, and — after the next evaluation — the *actual* gating outcome and
per-task attribution. This gives the optimizer/generator a memory so it does not
re-propose a hypothesis that was already tried and reverted.

Storage: ``extension/.journal/<module>/<name>.md`` — one markdown file per
component, one ``## Round N`` section per round. Machine-readable fields live in
an HTML-comment YAML block (agent-writable, human-readable); free prose follows.
Sits alongside ``.versions/`` and is git-ignored the same way.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from autogenesis.logger import logger
from autogenesis.utils import get_extension_root

_JOURNAL = ".journal"
_LEVERS = ("configuration", "control", "action", "instruction")
_ROUND_RE = re.compile(r"^## Round (\d+)\s*\n<!--\n(.*?)\n-->\n?(.*?)(?=^## Round |\Z)", re.DOTALL | re.MULTILINE)


class JournalRound(BaseModel):
    """One evolution round's hypothesis and (later) its measured outcome."""

    round: int
    hypothesis_id: str
    lever: str = Field(default="instruction", description="configuration | control | action | instruction")
    predicted_flip: List[str] = Field(default_factory=list, description="task_ids predicted to flip fail→pass")
    gating_outcome: str = Field(default="pending", description="pending | accepted | reverted | noop")
    gating_attribution: Dict[str, bool] = Field(default_factory=dict, description="task_id -> actually flipped")
    note: str = ""

    def render(self) -> str:
        fm = {
            "hypothesis_id": self.hypothesis_id,
            "lever": self.lever,
            "predicted_flip": self.predicted_flip,
            "gating_outcome": self.gating_outcome,
            "gating_attribution": self.gating_attribution,
        }
        block = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
        note = (self.note or "").strip()
        return f"## Round {self.round}\n<!--\n{block}\n-->\n{note}\n"


class Journal:
    """Read/append/attribute the per-component evolution journal."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        # Default to the same extension tree the ExtensionManager uses.
        self.base_dir = os.path.abspath(base_dir) if base_dir else get_extension_root()

    def _path(self, module: str, name: str) -> str:
        d = os.path.join(self.base_dir, _JOURNAL, module)
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{name}.md")

    def read(self, module: str, name: str) -> List[JournalRound]:
        path = self._path(module, name)
        if not os.path.exists(path):
            return []
        text = open(path, encoding="utf-8").read()
        rounds: List[JournalRound] = []
        for m in _ROUND_RE.finditer(text):
            try:
                fm = yaml.safe_load(m.group(2)) or {}
                rounds.append(JournalRound(
                    round=int(m.group(1)),
                    hypothesis_id=str(fm.get("hypothesis_id", "")),
                    lever=str(fm.get("lever", "instruction")),
                    predicted_flip=list(fm.get("predicted_flip") or []),
                    gating_outcome=str(fm.get("gating_outcome", "pending")),
                    gating_attribution=dict(fm.get("gating_attribution") or {}),
                    note=(m.group(3) or "").strip(),
                ))
            except Exception as e:
                logger.warning(f"| ⚠️ Journal: skipping malformed round in {path}: {e}")
        return sorted(rounds, key=lambda r: r.round)

    def _write(self, module: str, name: str, rounds: List[JournalRound]) -> None:
        path = self._path(module, name)
        body = "\n".join(r.render() for r in sorted(rounds, key=lambda r: r.round))
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Evolution journal — {module}:{name}\n\n{body}\n")

    def next_round_number(self, module: str, name: str) -> int:
        rounds = self.read(module, name)
        return (max((r.round for r in rounds), default=0)) + 1

    def append_round(self, module: str, name: str, hypothesis_id: str, lever: str = "instruction",
                     predicted_flip: Optional[List[str]] = None, note: str = "") -> JournalRound:
        """Record a new hypothesis for this round (gating_outcome starts 'pending')."""
        if lever not in _LEVERS:
            logger.warning(f"| ⚠️ Journal: unknown lever {lever!r}; expected one of {_LEVERS}")
        rounds = self.read(module, name)
        rnd = JournalRound(
            round=self.next_round_number(module, name),
            hypothesis_id=hypothesis_id,
            lever=lever,
            predicted_flip=predicted_flip or [],
            note=note,
        )
        rounds.append(rnd)
        self._write(module, name, rounds)
        logger.info(f"| 📓 Journal: {module}:{name} round {rnd.round} hypothesis '{hypothesis_id}' ({lever})")
        return rnd

    def fill_gating(self, module: str, name: str, outcome: str,
                    attribution: Optional[Dict[str, bool]] = None, round_no: Optional[int] = None) -> Optional[JournalRound]:
        """Backfill the actual outcome/attribution for a round (defaults to the latest pending one)."""
        rounds = self.read(module, name)
        if not rounds:
            return None
        target = None
        if round_no is not None:
            target = next((r for r in rounds if r.round == round_no), None)
        else:
            # latest pending round
            target = next((r for r in reversed(rounds) if r.gating_outcome == "pending"), None)
        if target is None:
            return None
        target.gating_outcome = outcome
        if attribution:
            target.gating_attribution = attribution
        self._write(module, name, rounds)
        logger.info(f"| 📓 Journal: {module}:{name} round {target.round} gated '{outcome}'")
        return target

    def reverted_hypotheses(self, module: str, name: str) -> List[str]:
        """Hypothesis ids the optimizer must NOT re-propose (already tried and reverted)."""
        return [r.hypothesis_id for r in self.read(module, name) if r.gating_outcome == "reverted"]

    def render_context(self, module: str, name: str) -> str:
        """A compact ribbon for the optimizer's prompt: what's been tried, predicted vs actual."""
        rounds = self.read(module, name)
        if not rounds:
            return f"(no prior evolution rounds for {module}:{name})"
        lines = [f"Prior evolution rounds for {module}:{name}:"]
        for r in rounds:
            flipped = [t for t, ok in r.gating_attribution.items() if ok]
            lines.append(
                f"- Round {r.round} [{r.lever}] hypothesis={r.hypothesis_id} "
                f"outcome={r.gating_outcome} predicted={r.predicted_flip} actually_flipped={flipped}"
            )
        reverted = self.reverted_hypotheses(module, name)
        if reverted:
            lines.append(f"DO NOT re-propose these reverted hypotheses: {reverted}")
        return "\n".join(lines)


# Global singleton
journal = Journal()

__all__ = ["JournalRound", "Journal", "journal"]
