import random
import pandas as pd

from autogenesis.registry import DATASET
from autogenesis.utils import assemble_workspace_path


@DATASET.register_module(force=True)
class GPQADataset:
    def __init__(self, path, name="gpqa_diamond", split="test"):
        """
        Initialize GPQA Dataset (HuggingFace `Idavidrein/gpqa` format — gated).

        Reads from a local snapshot directory (downloaded by `ensure_dataset`).
        Configs: gpqa_main / gpqa_diamond / gpqa_extended / gpqa_experts. Columns:
        Question, Correct Answer, Incorrect Answer 1/2/3, Record ID, Subdomain.

        Args:
            path: Local dataset directory (the HF snapshot).
            name: "all" or a specific config (e.g. "gpqa_diamond").
            split: Preferred split; falls back to whatever split exists.
        """
        from datasets import load_dataset, get_dataset_config_names

        self.path = path
        self.name = name
        self.split = split

        local_dir = assemble_workspace_path(path)
        try:
            all_configs = get_dataset_config_names(local_dir)
        except Exception:
            all_configs = []

        if name and name != "all" and (name in all_configs or not all_configs):
            target_configs = [name]
        elif all_configs:
            target_configs = all_configs
        else:
            target_configs = ["gpqa_diamond"]

        data_rows = []
        # Fixed seed so the A/B/C/D option order is reproducible across runs.
        rng = random.Random(42)

        for config in target_configs:
            ds = load_dataset(local_dir, name=config)
            split_name = split if split in ds else list(ds.keys())[0]
            for i, row in enumerate(ds[split_name]):
                q_text = str(row.get("Question", "")).strip()
                correct_ans = str(row.get("Correct Answer", "")).strip()
                if not q_text or not correct_ans:
                    continue

                choices = [correct_ans]
                for j in range(1, 4):
                    wrong = str(row.get(f"Incorrect Answer {j}", "")).strip()
                    if wrong:
                        choices.append(wrong)
                if len(choices) < 2:
                    continue

                rng.shuffle(choices)
                try:
                    correct_letter = chr(65 + choices.index(correct_ans))
                except ValueError:
                    continue

                options_str = "\n".join(f"{chr(65 + idx)}) {c}" for idx, c in enumerate(choices))
                full_question_prompt = f"{q_text}\n\n{options_str}\nAnswer:"

                rec_id = str(row.get("Record ID", "") or f"{config}_{i + 1}")
                data_rows.append({
                    "task_id": rec_id,
                    "question": full_question_prompt,
                    "true_answer": correct_letter,
                    "origin_answer": correct_ans,
                    "task": "GPQA",
                    "subset": config,
                    "subdomain": str(row.get("Subdomain", "")),
                    "file_name": "",
                })

        self.data = pd.DataFrame(data_rows)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data.iloc[index]

    def get_task_description(self):
        return """
Answer the following multiple choice question. The last line of your response should be of the following format: 'Answer: $LETTER' (without quotes) where LETTER is one of ABCD. Think step by step before answering.

{Question}

A) {A}
B) {B}
C) {C}
D) {D}
""".strip()
