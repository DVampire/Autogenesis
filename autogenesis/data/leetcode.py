import os
import json
import pandas as pd

from autogenesis.registry import DATASET
from autogenesis.utils import assemble_workspace_path


@DATASET.register_module(force=True)
class LeetCodeDataset:
    def __init__(self, path, name, split, lang="python3"):
        """
        Initialize LeetCode Dataset.
        
        Args:
            path: Base path to the dataset directory
            name: Dataset mode (e.g., "all", or "easy", "hard" if folders are split)
            split: Dataset split ("test", "validation", "train")
            lang: The target programming language for the code template (default: "python3")
                  Supported: "cpp", "java", "python3", "golang", "rust", etc.
        """
        self.path = path
        self.name = name
        self.split = split
        self.lang = lang

        # 1. Path normalization
        path = assemble_workspace_path(path)
        
        # 2. Load metadata file
        # Expected path structure: /data/leetcode/test/metadata.jsonl
        metadata_file = os.path.join(path, split, "metadata.jsonl")
        
        if not os.path.exists(metadata_file):
            raise FileNotFoundError(f"Metadata file not found: {metadata_file}")
        
        data_rows = []
        
        with open(metadata_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # --- LeetCode specific loading logic ---

                # 1. Read problem description (Markdown content)
                # row['file'] example: "./question/1.two_sum.md"
                # Parse to absolute path, usually relative to metadata.jsonl directory
                rel_file_path = row.get("file", "")
                question_content = ""
                
                metadata_dir = os.path.dirname(os.path.abspath(metadata_file))

                if rel_file_path:
                    raw_path = os.path.join(metadata_dir, rel_file_path)
                    abs_file_path = os.path.normpath(raw_path)
                    if os.path.exists(abs_file_path):
                        with open(abs_file_path, "r", encoding="utf-8") as qf:
                            question_content = qf.read()
                    else:
                        print(f"[Warning] 路径不存在: {abs_file_path}")
                        continue
                    
                code_template = row.get("code_template", {})
            

                # 4. Construct data row
                data_row = {
                    "task_id": str(row.get("id", "")), # to string
                    "name": row.get("name", ""),
                    "question": question_content,
                    
                    # LeetCode datasets are typically for Code Generation,
                    # real verification requires Sandbox execution,
                    # true_answer is usually empty or contains test cases (if any)
                    "true_answer": "", 
                    "code_template": code_template,
                    "lang": self.lang,
                    "task": "LeetCode",
                    "file_name": rel_file_path
                }
                
                data_rows.append(data_row)
        
        # 4. Convert to DataFrame
        self.data = pd.DataFrame(data_rows)
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, index):
        return self.data.iloc[index]
