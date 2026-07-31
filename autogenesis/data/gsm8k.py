import pandas as pd

from autogenesis.registry import DATASET
from autogenesis.utils import assemble_workspace_path


@DATASET.register_module(force=True)
class GSM8kDataset:
    def __init__(self, path, name="main", split="test"):
        """
        Initialize GSM8k Dataset (HuggingFace `openai/gsm8k` format).

        Reads from a local snapshot directory (downloaded by `ensure_dataset`).
        Configs: "main" / "socratic"; splits: train / test. Columns: question, answer
        (answer ends with a "#### <final>" line).

        Args:
            path: Local dataset directory (the HF snapshot).
            name: "all", "main", or "socratic".
            split: Dataset split ("test" / "train").
        """
        from datasets import load_dataset, get_dataset_config_names

        self.path = path
        self.name = name
        self.split = split

        local_dir = assemble_workspace_path(path)
        all_subsets = ["main", "socratic"]
        if name == "all":
            target_subsets = all_subsets
        elif name in all_subsets:
            target_subsets = [name]
        else:
            print(f"[Warning] Unknown subset '{name}'. Defaulting to 'main'.")
            target_subsets = ["main"]

        try:
            available = get_dataset_config_names(local_dir)
        except Exception:
            available = all_subsets
        target_subsets = [s for s in target_subsets if not available or s in available] or [target_subsets[0]]

        data_rows = []
        for subset_name in target_subsets:
            ds = load_dataset(local_dir, name=subset_name)
            split_name = split if split in ds else list(ds.keys())[0]
            for i, row in enumerate(ds[split_name]):
                raw_answer = str(row.get("answer", ""))
                if "####" in raw_answer:
                    parts = raw_answer.split("####")
                    reasoning_content = parts[0].strip()
                    final_answer = parts[-1].strip()
                else:
                    reasoning_content = ""
                    final_answer = raw_answer.strip()

                data_rows.append({
                    "task_id": f"{subset_name}_{i + 1}",
                    "question": str(row.get("question", "")),
                    "true_answer": final_answer.replace(",", ""),
                    "reasoning": reasoning_content,
                    "task": "GSM8k",
                    "subset": subset_name,
                    "file_name": "",
                })

        self.data = pd.DataFrame(data_rows)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data.iloc[index]

    def get_task_description(self):
        return "You will answer a mathemetical reasoning question. Think step by step. The last line of your response should be of the following format: 'Answer: $VALUE' where VALUE is a numerical value."
