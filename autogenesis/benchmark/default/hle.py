import base64
import os
import re
from typing import Optional, Any, List, Dict
from pydantic import Field, ConfigDict, PrivateAttr

from autogenesis.benchmark.types import Benchmark, Task, Stats
from autogenesis.registry import BENCHMARK
from autogenesis.utils import dedent
from autogenesis.utils import is_same

SYSTEM_PROMPT = dedent("""
    You are a helpful assistant that solves challenging academic questions across many subjects. Please think step by step, deliver both the reasoning and the result, and strictly follow the provided output format.

    Notes:
    - For multiple-choice questions, provide only the letter of the correct option (e.g. "A", "B", "C", "D").
    - For short-answer / exact-match questions, provide a concise answer string.
    - If an image is provided, use it carefully as part of your reasoning.
    
    Please solve the following problem:
""")


def _extract_image_media_type(data_uri: str) -> str:
    """Extract media type from a data URI like 'data:image/jpeg;base64,...'."""
    match = re.match(r"data:(image/\w+);", data_uri)
    if match:
        return match.group(1)
    return "image/png"


@BENCHMARK.register_module(force=True)
class HLEBenchmark(Benchmark):
    """
    Humanity's Last Exam (HLE) Benchmark – a multi-modal benchmark of 2500
    expert-level questions across dozens of academic subjects.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="hle", description="The name of the benchmark")
    path: str = Field(default="datasets/hle", description="The path to the benchmark dataset")
    hf_repo_id: str = Field(default="cais/hle", description="HuggingFace repo to download the dataset from when it is missing locally.")

    _data_records: List[Dict] = PrivateAttr(default_factory=list)
    _index: int = PrivateAttr(default=0)
    _tasks: List[Task] = PrivateAttr(default_factory=list)
    _tags: Dict[str, List[str]] = PrivateAttr(default_factory=dict)

    system_prompt: Optional[str] = Field(default=SYSTEM_PROMPT, description="The system prompt for the benchmark")

    def __init__(self, base_dir: Optional[str] = None, start: Optional[int] = None, end: Optional[int] = None, **kwargs):
        super().__init__(base_dir=base_dir, start=start, end=end, **kwargs)

    async def initialize(self):
        # Created on first use, not at construction: the registry builds every
        # benchmark at startup, before any session is bound, so doing it in
        # __init__ scaffolded empty directories under the unbound root.
        os.makedirs(self.base_dir, exist_ok=True)
        from datasets import load_dataset
        import pathlib
        from autogenesis.benchmark.utils import ensure_dataset
        import os
        local_path = pathlib.Path(ensure_dataset(os.path.basename(self.path), self.hf_repo_id))
        dataset = load_dataset(str(local_path), split="test")
        self._data_records = self._apply_slice(list(dataset))
        tags_path = local_path / "data" / "tags.json"
        if tags_path.exists():
            import json
            with open(tags_path) as f:
                self._tags = json.load(f)
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

        question_text = record.get("question", "")
        image_data = record.get("image")
        answer_type = record.get("answer_type", "exactMatch")

        if answer_type == "multipleChoice":
            question_text += "\n\nThis is a multiple-choice question. Provide only the letter of the correct option."

        extra = {
            k: v for k, v in record.items()
            if k not in ["true_answer", "answer", "task_id", "id", "question"]
        }
        global_index = (self.start or 0) + self._index
        task_id = record.get("task_id", f"{global_index:04d}")
        if task_id in self._tags:
            extra["tags"] = self._tags[task_id]

        if image_data:
            # image_data may be a PIL Image (from HuggingFace datasets) or a base64 data URI string
            try:
                from PIL import Image as PILImage
                is_pil = isinstance(image_data, PILImage.Image)
            except ImportError:
                is_pil = False

            if is_pil:
                fmt = (image_data.format or "PNG").lower().replace("jpeg", "jpg")
                media_type = f"image/{'jpeg' if fmt == 'jpg' else fmt}"
                image_path = os.path.join(self.base_dir, f"{task_id}.{fmt}")
                if not os.path.exists(image_path):
                    image_data.save(image_path)
            else:
                # base64 data URI fallback
                media_type = _extract_image_media_type(image_data)
                ext = media_type.split("/")[-1].replace("jpeg", "jpg")
                image_path = os.path.join(self.base_dir, f"{task_id}.{ext}")
                if not os.path.exists(image_path):
                    _, _, b64data = image_data.partition(",")
                    raw = base64.b64decode(b64data if b64data else image_data)
                    with open(image_path, "wb") as f:
                        f.write(raw)

            extra["image"] = image_path
            extra["image_media_type"] = media_type

        return Task(
            task_id=record.get("task_id", f"{self._index:04d}"),
            input=question_text,
            system_prompt=self.system_prompt,
            ground_truth=record.get("true_answer") or record.get("answer"),
            extra=extra,
        )

    async def eval(self, task: Task) -> Optional[Task]:
        result = str(task.result).strip() if task.result is not None else ""
        ground_truth = str(task.ground_truth).strip() if task.ground_truth is not None else ""

        task.result = result
        task.ground_truth = ground_truth

        if self.model_name:
            task.score = await self.llm_judge(task)
            self._tasks.append(task)
            return task

        task.score = 1.0 if result and is_same(result, ground_truth) else 0.0

        self._tasks.append(task)
        return task

    async def stats(self) -> Optional[Stats]:
        total = len(self._data_records)
        attempted = len(self._tasks)
        correct = sum(1 for r in self._tasks if r.score and r.score >= 1.0)

        task_times = {r.task_id: r.time for r in self._tasks if r.time is not None}
        avg_time = sum(task_times.values()) / len(task_times) if task_times else 0.0

        mc_tasks = [t for t in self._tasks if t.extra and t.extra.get("answer_type") == "multipleChoice"]
        em_tasks = [t for t in self._tasks if t.extra and t.extra.get("answer_type") == "exactMatch"]

        mc_correct = sum(1 for t in mc_tasks if t.score and t.score >= 1.0)
        em_correct = sum(1 for t in em_tasks if t.score and t.score >= 1.0)

        return Stats(
            accuracy=correct / attempted if attempted > 0 else 0.0,
            total=total,
            correct=correct,
            wrong=attempted - correct,
            times=task_times,
            average_time=avg_time,
            extra={
                "multiple_choice_accuracy": mc_correct / len(mc_tasks) if mc_tasks else 0.0,
                "exact_match_accuracy": em_correct / len(em_tasks) if em_tasks else 0.0,
                "multiple_choice_total": len(mc_tasks),
                "exact_match_total": len(em_tasks),
            },
        )

