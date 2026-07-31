"""A dataset-free evaluator: score predictions against ground truth.

Unlike the dataset-bound benchmarks (gsm8k, aime, …) that download their own
data, ``exact_match`` scores whatever ``{prediction, ground_truth}`` pairs are
handed to it — so it is the general evaluator a canvas ``benchmark`` node uses
to close a data pipeline (``… -> to_eval_records -> benchmark``). It has no
dataset, so ``initialize()`` is a no-op and startup stays cheap.
"""

from typing import List, Optional

from pydantic import PrivateAttr

from autogenesis.registry import BENCHMARK
from autogenesis.benchmark.types import Benchmark, Stats, Task


@BENCHMARK.register_module(force=True)
class ExactMatchBenchmark(Benchmark):
    """Score predictions against ground truth (numeric-tolerant exact match)."""

    name: str = "exact_match"
    description: str = "Evaluate {prediction, ground_truth} pairs by numeric/exact match."

    _tasks: List[Task] = PrivateAttr(default_factory=list)

    async def initialize(self):
        """No dataset to load."""
        self._tasks = []

    async def reset(self) -> Optional[Task]:
        self._tasks = []
        return None

    async def step(self) -> Optional[Task]:
        return None

    async def eval(self, task: Task) -> Optional[Task]:
        """1.0 when the prediction equals the ground truth (numeric or string)."""
        pred = str(task.result).strip() if task.result is not None else ""
        gt = str(task.ground_truth).strip() if task.ground_truth is not None else ""
        score = 0.0
        if pred:
            try:
                score = 1.0 if abs(float(pred) - float(gt)) < 1e-9 else 0.0
            except (TypeError, ValueError):
                score = 1.0 if pred == gt else 0.0
        task.score = score
        self._tasks.append(task)
        return task

    async def stats(self) -> Optional[Stats]:
        total = len(self._tasks)
        correct = sum(1 for task in self._tasks if (task.score or 0.0) >= 1.0)
        return Stats(accuracy=(correct / total if total else 0.0), total=total,
                     correct=correct, wrong=total - correct)
