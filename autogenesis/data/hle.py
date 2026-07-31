import os
import pandas as pd

from autogenesis.registry import DATASET
from autogenesis.utils import assemble_workspace_path


@DATASET.register_module(force=True)
class HLEDataset:
    def __init__(self, path, name, split):
        """
        Initialize Humanity's Last Exam (HLE) Dataset.

        Args:
            path: Base path to the dataset directory
            name: Dataset name / config ("default" or "all")
            split: Dataset split ("test")
        """
        self.path = path
        self.name = name
        self.split = split

        path = assemble_workspace_path(path)

        parquet_dir = os.path.join(path, "data")
        parquet_files = [
            os.path.join(parquet_dir, f)
            for f in os.listdir(parquet_dir)
            if f.endswith(".parquet")
        ]
        if not parquet_files:
            raise FileNotFoundError(f"No parquet files found in: {parquet_dir}")

        raw_df = pd.concat([pd.read_parquet(f) for f in sorted(parquet_files)], ignore_index=True)

        data_rows = []
        for _, row in raw_df.iterrows():
            question = str(row.get("question", "")).strip()
            if not question:
                continue

            image_data = row.get("image")
            has_image = isinstance(image_data, str) and image_data.strip() != ""

            data_row = {
                "task_id": str(row.get("id", "")),
                "question": question,
                "true_answer": str(row.get("answer", "")),
                "answer_type": str(row.get("answer_type", "exactMatch")),
                "image": image_data if has_image else None,
                "category": str(row.get("category", "")),
                "raw_subject": str(row.get("raw_subject", "")),
                "task": "HLE",
            }
            data_rows.append(data_row)

        self.data = pd.DataFrame(data_rows)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data.iloc[index]
