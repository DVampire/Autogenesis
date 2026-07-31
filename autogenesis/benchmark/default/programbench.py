import os
import shutil
import subprocess
import sys
import tarfile
from typing import Optional, List, Dict, Any

from pydantic import Field, ConfigDict, PrivateAttr

from autogenesis.benchmark.types import Benchmark, Task, Stats
from autogenesis.registry import BENCHMARK
from autogenesis.logger import logger
from autogenesis.utils import dedent

SYSTEM_PROMPT = dedent("""
    You are an expert software engineer. You are given only a compiled binary of a
    program together with its documentation, running inside an offline sandbox.
    Your task is to architect and implement, from scratch, a complete codebase that
    reproduces the original program's observable behavior as faithfully as possible.

    Work entirely from the binary and the documentation — you have no internet access
    and no access to the original source code. Your final deliverable is the complete
    source tree of your reconstructed program.

    Task:
""")


@BENCHMARK.register_module(force=True)
class ProgramBenchmark(Benchmark):
    """
    ProgramBench – agents must rebuild a complete codebase that reproduces a program's
    behavior given only its compiled binary and documentation. Scored by running the
    hidden test suites against the agent's reconstructed codebase (passed / total).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="programbench", description="The name of the benchmark")
    # Task definitions (task.yaml/tests.json) ship with the `programbench` pip package.
    # `path`/`hf_repo_id` govern the per-branch TEST BLOBS, read locally first and
    # downloaded from HuggingFace on demand by the official evaluator.
    path: str = Field(default="datasets/ProgramBench-Tests", description="Local directory holding the per-branch test blobs.")
    hf_repo_id: str = Field(default="programbench/ProgramBench-Tests", description="HuggingFace repo to download the test blobs from when missing locally.")

    # Evaluation knobs (passed through to the `programbench eval` CLI)
    docker_cpus: int = Field(default=10, description="CPU cores allotted per docker container during evaluation.")
    branch_workers: int = Field(default=1, description="Number of test branches to run in parallel within an instance.")
    eval_timeout: int = Field(default=3600, description="Per-task timeout (seconds) for the `programbench eval` subprocess.")

    _data_records: List[Dict] = PrivateAttr(default_factory=list)
    _instances: Dict[str, Dict] = PrivateAttr(default_factory=dict)
    _index: int = PrivateAttr(default=0)
    _tasks: List[Task] = PrivateAttr(default_factory=list)

    system_prompt: Optional[str] = Field(default=SYSTEM_PROMPT, description="The system prompt for the benchmark")

    def __init__(self, base_dir: Optional[str] = None, start: Optional[int] = None, end: Optional[int] = None, **kwargs):
        super().__init__(base_dir=base_dir, start=start, end=end, **kwargs)

    async def initialize(self):
        # Created on first use, not at construction: the registry builds every
        # benchmark at startup, before any session is bound, so doing it in
        # __init__ scaffolded empty directories under the unbound root.
        os.makedirs(self.base_dir, exist_ok=True)
        # Ensure the test blobs exist locally (download from HF on first use), then
        # point the official evaluator at them so it runs fully offline.
        from autogenesis.benchmark.utils import ensure_dataset
        blob_dir = ensure_dataset(os.path.basename(self.path), self.hf_repo_id)
        os.environ["PROGRAMBENCH_BLOB_DIR"] = blob_dir

        from autogenesis.data.programbench import ProgramBenchDataset
        dataset = ProgramBenchDataset()
        self._instances = dataset.instances
        self._data_records = self._apply_slice(dataset.data)
        await self.reset()

    async def reset(self) -> Optional[Task]:
        self._index = 0
        self._tasks = []
        return await self.step()

    async def step(self) -> Optional[Task]:
        if self._index >= len(self._data_records):
            return None

        record = self._data_records[self._index]
        self._index += 1

        instance_id = record["instance_id"]
        repository = record.get("repository", "")
        commit = record.get("commit", "")
        language = record.get("language", "")
        image_name = record.get("image_name", "")

        question = dedent(f"""
            Reconstruct the program `{repository}` (language: {language}).

            A compiled binary and its documentation are available in your sandbox
            (task image: `{image_name}`, commit `{commit}`). Implement a complete
            codebase that reproduces the program's behavior. Produce the full source
            tree as your final answer.
        """)

        extra = {
            "instance_id": instance_id,
            "repository": repository,
            "commit": commit,
            "language": language,
            "difficulty": record.get("difficulty"),
            "image_name": image_name,
        }

        return Task(
            task_id=instance_id,
            input=question,
            system_prompt=self.system_prompt,
            ground_truth=None,  # ground truth is the hidden test suite, applied during eval
            extra=extra,
        )

    def _prepare_submission(self, task_id: str, result: Any) -> Optional[str]:
        """Lay out a `programbench eval` run directory holding <task_id>/submission.tar.gz.

        `result` may be the path to a `.tar.gz` archive or to a source-tree directory.
        Returns the run directory path, or None if no usable submission was provided.
        """
        if not result:
            return None
        src_path = str(result).strip()
        if not src_path or not os.path.exists(src_path):
            logger.warning(f"[{self.name}] submission path does not exist for task {task_id}: {src_path!r}")
            return None

        log_root = os.path.join(self.base_dir, "eval_runs", task_id)
        inst_dir = os.path.join(log_root, task_id)
        os.makedirs(inst_dir, exist_ok=True)
        submission = os.path.join(inst_dir, "submission.tar.gz")

        if os.path.isdir(src_path):
            # Tar the source tree (members relative to the tree root).
            if os.path.exists(submission):
                os.remove(submission)
            with tarfile.open(submission, "w:gz") as tar:
                for entry in sorted(os.listdir(src_path)):
                    tar.add(os.path.join(src_path, entry), arcname=entry)
        elif src_path.endswith((".tar.gz", ".tgz")):
            shutil.copyfile(src_path, submission)
        else:
            logger.warning(f"[{self.name}] unsupported submission for task {task_id}: {src_path!r}")
            return None

        return log_root

    def _programbench_cli(self) -> Optional[str]:
        exe = os.path.join(os.path.dirname(sys.executable), "programbench")
        if os.path.exists(exe):
            return exe
        return shutil.which("programbench")

    async def eval(self, task: Task) -> Optional[Task]:
        task_id = task.task_id
        instance = self._instances.get(task_id)
        task.score = 0.0

        if instance is None:
            logger.error(f"[{self.name}] unknown instance: {task_id}")
            self._tasks.append(task)
            return task

        log_root = self._prepare_submission(task_id, task.result)
        if log_root is None:
            self._tasks.append(task)
            return task

        cli = self._programbench_cli()
        if cli is None:
            logger.error(f"[{self.name}] `programbench` CLI not found; cannot evaluate {task_id}.")
            self._tasks.append(task)
            return task

        cmd = [
            cli, "eval", log_root,
            "--filter", f"^{task_id}$",
            "--branch-workers", str(self.branch_workers),
            "--docker-cpus", str(self.docker_cpus),
            "--force",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.eval_timeout
            )
            if proc.returncode != 0:
                logger.warning(f"[{self.name}] `programbench eval` returned {proc.returncode} for {task_id}: {proc.stderr[-500:]}")
        except subprocess.TimeoutExpired:
            logger.error(f"[{self.name}] `programbench eval` timed out for {task_id}.")
            self._tasks.append(task)
            return task
        except Exception as e:
            logger.error(f"[{self.name}] `programbench eval` failed for {task_id}: {e}")
            self._tasks.append(task)
            return task

        # Score the produced eval.json with the same ignore-aware logic as `programbench info`.
        import pathlib
        from programbench.submission import score_instance, test_results_map
        eval_json = pathlib.Path(log_root) / task_id / f"{task_id}.eval.json"
        if not eval_json.exists():
            logger.warning(f"[{self.name}] no eval.json produced for {task_id}.")
            self._tasks.append(task)
            return task

        try:
            task.score = score_instance(eval_json, instance)
            tests = test_results_map(eval_json, instance)
            passed = sum(1 for v in tests.values() if v)
            total = len(tests)
            task.extra = task.extra or {}
            task.extra.update({"passed_tests": passed, "total_tests": total, "eval_json": str(eval_json)})
        except Exception as e:
            logger.error(f"[{self.name}] failed to score {task_id}: {e}")
            task.score = 0.0

        self._tasks.append(task)
        return task

    async def stats(self) -> Optional[Stats]:
        total = len(self._data_records)
        attempted = len(self._tasks)
        # A task is "resolved" only when all (non-ignored) tests pass.
        resolved = sum(1 for r in self._tasks if r.score and r.score >= 1.0)
        mean_score = sum(r.score or 0.0 for r in self._tasks) / attempted if attempted > 0 else 0.0

        task_times = {r.task_id: r.time for r in self._tasks if r.time is not None}
        avg_time = sum(task_times.values()) / len(task_times) if task_times else 0.0

        return Stats(
            accuracy=mean_score,  # mean fraction of tests passed across tasks
            total=total,
            correct=resolved,
            wrong=attempted - resolved,
            times=task_times,
            average_time=avg_time,
            extra={
                "resolved": resolved,
                "resolved_rate": resolved / attempted if attempted > 0 else 0.0,
                "mean_test_pass_rate": mean_score,
            },
        )
