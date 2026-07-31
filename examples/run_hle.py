"""Run HLE (Humanity's Last Exam) evaluation end-to-end.

Pipeline (current framework): for each HLE question the benchmark yields a Task; an
answering agent (default `general_agent`) produces an answer; the benchmark scores it
(LLM judge when a judge model is configured, else exact match); results + a summary are
written to a JSON file under the run dir.

Usage:
    python examples/run_hle.py --start 0 --end 5 --max-concurrency 4    # smoke test
    python examples/run_hle.py --max-concurrency 16                     # full run
    python examples/run_hle.py --stats  <results.json>                  # print summary only
    python examples/run_hle.py --resume <results.json>                  # skip already-answered
    python examples/run_hle.py --eval-only --resume <results.json>      # re-judge only

Note: the old guide referenced a bus/planner/opencode pipeline and a viewer.html — those
are not part of this repo; this runner uses the current agent + benchmark managers.
"""
import os
import sys
import json
import time
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from argparse import Namespace

from dotenv import load_dotenv

load_dotenv(verbose=True)

from mmengine import DictAction

root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.version import version_manager
from autogenesis.model import model_manager
from autogenesis.prompt import prompt_manager
from autogenesis.memory import memory_manager
from autogenesis.tool import tool_manager
from autogenesis.skill import skill_manager
from autogenesis.connector import connector_manager
from autogenesis.agent import agent_manager
from autogenesis.benchmark import benchmark_manager
from autogenesis.hook import hook_manager


def parse_args():
    p = argparse.ArgumentParser(description="Run HLE evaluation")
    p.add_argument("--config", default=os.path.join(root, "configs", "hle.py"),
                   help="Config file (default: configs/hle.py).")
    p.add_argument("--agent", default="general_agent", help="Answering agent name.")
    p.add_argument("--start", type=int, default=None, help="Evaluate only the [start, end) range.")
    p.add_argument("--end", type=int, default=None, help="Evaluate only the [start, end) range.")
    p.add_argument("--max-concurrency", type=int, default=16, help="Concurrent answering tasks.")
    p.add_argument("--stats", nargs="?", const="", default=None,
                   help="Print the summary of a results JSON and exit (optionally pass the path).")
    p.add_argument("--resume", default=None, help="Resume from a results JSON (skip answered tasks).")
    p.add_argument("--eval-only", action="store_true", help="Re-judge answers in --resume without re-answering.")
    p.add_argument("--out", default=None, help="Results output directory (default: <log_root>/results/hle).")
    p.add_argument("--cfg-options", nargs="+", action=DictAction, help="Override config options.")
    return p.parse_args()


def _extract_answer(resp) -> str:
    """Pull the final answer string out of an agent Response (best effort)."""
    if resp is None:
        return ""
    data = getattr(resp, "data", None)
    if isinstance(data, dict):
        for k in ("result", "answer", "final_answer", "output"):
            if data.get(k):
                return str(data[k]).strip()
    msg = getattr(resp, "message", None)
    if msg:
        return str(msg).strip()
    return str(resp).strip()


async def _bootstrap(args):
    config.initialize(config_path=args.config, args=args)
    logger.initialize(config=config)
    await version_manager.initialize()
    await hook_manager.initialize()
    await model_manager.initialize()
    await prompt_manager.initialize()
    await memory_manager.initialize(memory_names=getattr(config, "memory_names", None))
    await tool_manager.initialize(tool_names=getattr(config, "tool_names", None))
    await skill_manager.initialize(skill_names=getattr(config, "skill_names", None))
    await connector_manager.initialize(connector_names=getattr(config, "connector_names", None))
    await agent_manager.initialize(agent_names=getattr(config, "agent_names", None))
    await benchmark_manager.initialize(benchmark_names=getattr(config, "benchmark_names", None))


def _results_path(args) -> str:
    out_dir = args.out or os.path.join(config.log_root, "results", "hle")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(out_dir, f"benchmark_hle_{ts}.json")


def _write_results(path: str, records: list, summary: dict):
    payload = {"summary": summary, "records": records}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)


async def _answer_all(tasks, agent_name, max_concurrency):
    """Answer every task concurrently via the agent, filling task.result."""
    sem = asyncio.Semaphore(max_concurrency)
    done = {"n": 0}

    async def answer(task):
        async with sem:
            t0 = time.time()
            try:
                resp = await agent_manager(agent_name, input={"task": task.input})
                task.result = _extract_answer(resp)
            except Exception as e:  # noqa: BLE001
                logger.error(f"| ❌ answering {task.task_id} failed: {e}")
                task.result = ""
            task.time = time.time() - t0
            done["n"] += 1
            mark = "✅" if task.result else "❌"
            logger.info(f"| {mark} [{done['n']}/{len(tasks)}] {task.task_id} answered in {task.time:.1f}s")

    await asyncio.gather(*[answer(t) for t in tasks])


async def main():
    args = parse_args()

    # --stats: just summarize an existing results file.
    if args.stats is not None:
        path = args.stats or args.resume
        if not path or not os.path.exists(path):
            print("usage: --stats <results.json>")
            return
        data = json.load(open(path, encoding="utf-8"))
        print(json.dumps(data.get("summary", {}), indent=2, ensure_ascii=False))
        return

    # Slice override before the benchmark builds its task list.
    if args.start is not None or args.end is not None:
        hb = getattr(config, "hle_benchmark", None)
        if isinstance(hb, dict):
            if args.start is not None:
                hb["start"] = args.start
            if args.end is not None:
                hb["end"] = args.end

    await _bootstrap(args)

    # Collect every task (reset yields the first, step the rest).
    tasks = []
    t = await benchmark_manager.reset("hle")
    while t is not None:
        tasks.append(t)
        t = await benchmark_manager.step("hle")
    logger.info(f"| 🧪 HLE: {len(tasks)} question(s) to evaluate")

    # Resume: carry over answers already present for matching task_ids.
    prior = {}
    if args.resume and os.path.exists(args.resume):
        for r in json.load(open(args.resume, encoding="utf-8")).get("records", []):
            prior[r.get("task_id")] = r
        for tk in tasks:
            p = prior.get(tk.task_id)
            if p and p.get("result"):
                tk.result = p["result"]

    if not args.eval_only:
        todo = [tk for tk in tasks if not (tk.result and str(tk.result).strip())]
        logger.info(f"| ▶️ answering {len(todo)} task(s) (resumed {len(tasks) - len(todo)})")
        await _answer_all(todo, args.agent, args.max_concurrency)

    # Judge every task.
    for tk in tasks:
        await benchmark_manager.eval("hle", tk)

    stats = await benchmark_manager.stats("hle")
    summary = stats.model_dump() if hasattr(stats, "model_dump") else (stats or {})
    records = [tk.model_dump() for tk in tasks]

    out_path = _results_path(args)
    _write_results(out_path, records, summary)

    acc = summary.get("accuracy", 0.0) if isinstance(summary, dict) else 0.0
    total = summary.get("total", len(tasks)) if isinstance(summary, dict) else len(tasks)
    correct = summary.get("correct", 0) if isinstance(summary, dict) else 0
    print(f"\n✅ HLE done: {correct}/{total} correct, accuracy={acc:.4f}")
    print(f"   Results: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
