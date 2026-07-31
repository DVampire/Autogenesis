import pandas as pd

from autogenesis.registry import DATASET
from autogenesis.utils import assemble_workspace_path


@DATASET.register_module(force=True)
class AIME25Dataset:
    def __init__(self, path, name="all", split="test", **kwargs):
        """
        Initialize AIME 2025 Dataset (HuggingFace `opencompass/AIME2025` format).

        Reads from a local snapshot directory (downloaded by `ensure_dataset`).
        The source has two configs (AIME2025-I, AIME2025-II), each with a `test`
        split and columns: question, answer.

        Args:
            path: Local dataset directory (the HF snapshot).
            name: "all" to load both parts, or a specific config name.
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

        if name and name != "all" and name in all_configs:
            target_configs = [name]
        elif all_configs:
            target_configs = all_configs
        else:
            target_configs = [None]

        data_rows = []
        for config in target_configs:
            ds = load_dataset(local_dir, name=config) if config else load_dataset(local_dir)
            split_name = split if split in ds else list(ds.keys())[0]
            for i, row in enumerate(ds[split_name]):
                q_text = str(row.get("question", "")).strip()
                if not q_text:
                    continue
                raw_id = row.get("ID") or row.get("id") or f"{config or 'aime25'}_{i + 1}"
                data_rows.append({
                    "task_id": str(raw_id),
                    "question": q_text,
                    "true_answer": str(row.get("answer", "")).strip(),
                    "task": "AIME 2025",
                    "subset": config or "",
                    "file_name": "",
                })

        self.data = pd.DataFrame(data_rows)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data.iloc[index]
