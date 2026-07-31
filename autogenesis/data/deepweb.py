import json
import os

from autogenesis.registry import DATASET
from autogenesis.utils import assemble_workspace_path


@DATASET.register_module(force=True)
class DeepWebDataset:
    def __init__(self, path, name=None, split=None):
        """
        Initialize DEEPWEB-BENCH Dataset (deep-research QA cases).

        Reads from a local snapshot directory (downloaded by `ensure_dataset`).
        Data lives in `<path>/data/cases.jsonl`; each row is a benchmark case with
        fields such as case_id, question_md, reference_answer_md, scoring_rubric_md,
        dimensions, entities, domain, ...

        Args:
            path: Local dataset directory (the HF snapshot).
            name: Unused; kept for signature compatibility.
            split: Unused; kept for signature compatibility.
        """
        self.path = path
        self.name = name
        self.split = split

        local_dir = assemble_workspace_path(path)
        cases_path = os.path.join(local_dir, "data", "cases.jsonl")

        records = []
        with open(cases_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        # Kept as a list of raw dicts to preserve nested fields (lists/dicts) intact.
        self.data = records

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data[index]
