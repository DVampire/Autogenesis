import pandas as pd

from autogenesis.registry import DATASET
from autogenesis.utils import assemble_workspace_path


@DATASET.register_module(force=True)
class AIME24Dataset:
    def __init__(self, path, name=None, split="test"):
        """
        Initialize AIME 2024 Dataset (HuggingFace `Maxwell-Jia/AIME_2024` format).

        Reads from a local snapshot directory (downloaded by `ensure_dataset`).
        Columns in the source: ID, Problem, Solution, Answer (single split: train).

        Args:
            path: Local dataset directory (the HF snapshot).
            name: Unused (single config); kept for signature compatibility.
            split: Preferred split; falls back to whatever split exists.
        """
        from datasets import load_dataset

        self.path = path
        self.name = name
        self.split = split

        local_dir = assemble_workspace_path(path)
        ds = load_dataset(local_dir)

        # AIME_2024 ships a single split ("train"); use the requested split if present.
        split_name = split if split in ds else list(ds.keys())[0]
        records = ds[split_name]

        data_rows = []
        for row in records:
            q_text = str(row.get("Problem", "")).strip()
            if not q_text:
                continue
            answer = row.get("Answer", "")
            if isinstance(answer, (int, float)):
                answer = str(int(answer))
            data_rows.append({
                "task_id": str(row.get("ID", "")),
                "question": q_text,
                "true_answer": str(answer).strip(),
                "reasoning": str(row.get("Solution", "")).strip(),
                "task": "AIME 2024",
                "file_name": "",
            })

        self.data = pd.DataFrame(data_rows)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data.iloc[index]
