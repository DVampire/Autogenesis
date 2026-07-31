"""Data Manager — HuggingFace-native dataset save/load.

The ``data`` module owns Autogenesis's dataset *assets*, unified on the
HuggingFace ``datasets`` format: a :class:`datasets.Dataset` is the canonical
representation for both directions, and the storage backend (the Hub or a local
path) is just a parameter. So a dataset pushed to the Hub and one saved locally
load back identically.

    [datasource] → [process] → [dataset_save · hub] → a shareable HF dataset
                                                       ↑ benchmark / training load it by repo id

``dataset_save`` pushes records to the Hub (or saves them locally); ``dataset_load``
reads a dataset from the Hub (or a local path) back into records. Both return the
canonical ``{message, data, files}`` envelope. The HF token is a settable
parameter, falling back to ``HF_TOKEN``; record schemas are auto-aligned.
"""

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.response.types import Response, ResponseType
from autogenesis.utils import assemble_workspace_path

# The named operations this manager exposes as canvas ``data`` nodes.
DATA_OPERATIONS: Dict[str, str] = {
    "dataset_save": "Save records as a HuggingFace dataset (push to the Hub or save locally).",
    "dataset_load": "Load a HuggingFace dataset (from the Hub or a local path) into records.",
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _coerce_records(records: Any, data: Any) -> List[Dict[str, Any]]:
    """Pull a list of records out of an upstream arg (list, JSON string, or a
    ``{records: [...]}`` data envelope)."""
    if isinstance(records, str):
        text = records.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                records = json.loads(text)
            except (ValueError, TypeError):
                records = None
    if isinstance(records, dict) and isinstance(records.get("records"), list):
        return records["records"]
    if isinstance(records, list):
        return records
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return data["records"]
    if isinstance(data, list):
        return data
    return []


def _align_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Give every record the same columns (union of keys; missing → None), which
    HuggingFace/pyarrow requires for a consistent schema."""
    keys: List[str] = []
    seen = set()
    for record in records:
        if isinstance(record, dict):
            for key in record:
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
    return [{key: record.get(key) for key in keys} for record in records if isinstance(record, dict)]


def _resolve_token(token: str) -> Optional[str]:
    """Prefer the node's token param, else HF_TOKEN / config; None = anonymous."""
    return (str(token).strip() if token else "") or os.environ.get("HF_TOKEN") or config.get("hf_token") or None


class DataManager(BaseModel):
    """Save/load HuggingFace datasets (Hub or local)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: Optional[str] = Field(default=None, description="Directory for locally-saved datasets.")

    async def initialize(self, data_names: Optional[List[str]] = None,
                         base_dir: Optional[str] = None) -> None:
        """Resolve the local datasets directory (created lazily on first save).

        ``base_dir`` overrides it; without one it follows ``config.log_root``,
        which a bound session repoints at its own directory.
        """
        self.base_dir = assemble_workspace_path(
            base_dir or self.base_dir or os.path.join(config.log_root, "datasets"))
        logger.info(f"| 🗂️ Data manager datasets directory: {self.base_dir}")
        logger.info("| ✅ Data manager initialization completed")

    async def list(self) -> List[str]:
        """The callable data operations (not the datasets themselves)."""
        return list(DATA_OPERATIONS.keys())

    async def get_info(self, name: str) -> Optional["_OperationInfo"]:
        """Descriptor for a data operation, or None if unknown."""
        description = DATA_OPERATIONS.get(name)
        return _OperationInfo(name=name, description=description) if description else None

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Data operations accept free-form args; no strict call schema."""
        return None

    def _local_path(self, repo: str) -> str:
        safe = _SAFE_NAME.sub("_", str(repo or "").strip()).strip("_") or "dataset"
        return os.path.join(self.base_dir or ".", safe)

    async def __call__(self, name: str, input: Dict[str, Any], ctx: Any = None, **kwargs) -> Response:
        """Dispatch a data operation (dataset_save / dataset_load)."""
        payload = input or {}
        if name == "dataset_save":
            return await self._save(payload)
        if name == "dataset_load":
            return await self._load(payload)
        return Response(type=ResponseType.TOOL, success=False, message=f"Unknown data operation: {name}")

    async def _save(self, payload: Dict[str, Any]) -> Response:
        repo = payload.get("repo") or payload.get("name") or payload.get("dataset")
        if not repo:
            return Response(type=ResponseType.TOOL, success=False, message="dataset_save: 'repo' is required.")
        records = _align_records(_coerce_records(payload.get("records"), payload.get("data")))
        target = str(payload.get("target") or "hub").lower()
        split = str(payload.get("split") or "train")
        try:
            from datasets import Dataset
        except ImportError:
            return Response(type=ResponseType.TOOL, success=False, message="dataset_save: 'datasets' is not installed.")

        try:
            dataset = Dataset.from_list(records)
            if target == "hub":
                token = _resolve_token(payload.get("token", ""))
                await asyncio.to_thread(
                    dataset.push_to_hub, repo, split=split,
                    private=bool(payload.get("private")), token=token,
                )
                url = f"https://huggingface.co/datasets/{repo}"
                return Response(
                    type=ResponseType.TOOL, success=True,
                    message=f"Pushed {len(records)} record(s) to HF dataset '{repo}' (split={split}).",
                    data={"repo": str(repo), "target": "hub", "split": split, "count": len(records), "url": url},
                )
            path = self._local_path(repo)
            await asyncio.to_thread(dataset.save_to_disk, path)
            return Response(
                type=ResponseType.TOOL, success=True,
                message=f"Saved {len(records)} record(s) to local dataset '{repo}'.",
                data={"repo": str(repo), "target": "local", "path": path, "count": len(records)},
                files=[path],
            )
        except Exception as exc:  # noqa: BLE001 — HF/network/auth errors are a failed result
            logger.error(f"| ❌ dataset_save failed: {exc}")
            return Response(type=ResponseType.TOOL, success=False, message=f"dataset_save: {exc}")

    async def _load(self, payload: Dict[str, Any]) -> Response:
        repo = payload.get("repo") or payload.get("name") or payload.get("dataset")
        if not repo:
            return Response(type=ResponseType.TOOL, success=False, message="dataset_load: 'repo' is required.")
        source = str(payload.get("source") or "hub").lower()
        split = str(payload.get("split") or "train")
        try:
            from datasets import load_dataset, load_from_disk
        except ImportError:
            return Response(type=ResponseType.TOOL, success=False, message="dataset_load: 'datasets' is not installed.")

        try:
            if source == "hub":
                token = _resolve_token(payload.get("token", ""))
                dataset = await asyncio.to_thread(load_dataset, repo, split=split, token=token)
            else:
                dataset = await asyncio.to_thread(load_from_disk, self._local_path(repo))
            # A split-less load returns a DatasetDict; pick the requested/first split.
            if hasattr(dataset, "keys") and not hasattr(dataset, "to_list"):
                dataset = dataset.get(split) or next(iter(dataset.values()))
            records = dataset.to_list()
            return Response(
                type=ResponseType.TOOL, success=True,
                message=f"Loaded {len(records)} record(s) from dataset '{repo}' (split={split}).",
                data={"repo": str(repo), "source": source, "split": split, "records": records, "count": len(records)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"| ❌ dataset_load failed: {exc}")
            return Response(type=ResponseType.TOOL, success=False, message=f"dataset_load: {exc}")

    async def cleanup(self) -> None:
        """No resources to release."""


class _OperationInfo(BaseModel):
    """Minimal descriptor so validation/catalog can read a name + description."""

    name: str
    description: str = ""


data_manager = DataManager()
