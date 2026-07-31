from autogenesis.registry import DATASET


@DATASET.register_module(force=True)
class ProgramBenchDataset:
    def __init__(self, path=None, name=None, split=None):
        """
        Initialize ProgramBench Dataset (codebase-reconstruction instances).

        The task definitions (task.yaml / tests.json) ship with the `programbench`
        pip package; the per-branch test blobs live under `datasets/ProgramBench-Tests`
        (ensured/downloaded separately by the benchmark). Each instance dict carries
        instance_id, repository, commit, language, difficulty, image_name, branches.

        Args:
            path: Unused for task definitions (they come from the pip package); kept
                  for signature compatibility.
            name: Unused; kept for signature compatibility.
            split: Unused; kept for signature compatibility.
        """
        self.path = path
        self.name = name
        self.split = split

        from programbench.utils.load_data import load_all_instances
        instances = load_all_instances(include_tests=True)

        self.data = instances
        self.instances = {i["instance_id"]: i for i in instances}

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data[index]
