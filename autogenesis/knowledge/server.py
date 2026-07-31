"""Knowledge Manager — RAG over named knowledge bases.

Owns the corpora (each a named knowledge base persisted as JSONL under the
knowledge dir) and delegates ranking to a pluggable :class:`RagBackend` type
selected per base. Exposes two operations as canvas nodes:

    knowledge_ingest — add documents to a base (records / strings / text).
    knowledge_retrieve — semantic search a base → top-k records with scores.

Both return the canonical ``{message, data, files}`` envelope.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import inflection
from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.registry import KNOWLEDGE
from autogenesis.response.types import Response, ResponseType
from autogenesis.utils import assemble_workspace_path
from autogenesis.knowledge.types import KnowledgeContext, RagBackend

KNOWLEDGE_OPERATIONS: Dict[str, str] = {
    "knowledge_ingest": "Add documents to a knowledge base (chunk-free; one record per document).",
    "knowledge_retrieve": "Retrieve the top-k most relevant documents from a knowledge base.",
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _coerce_documents(documents: Any, data: Any, text_field: str) -> List[Dict[str, Any]]:
    """Normalize an upstream arg to a list of ``{text, ...}`` documents."""
    if isinstance(documents, str):
        text = documents.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                documents = json.loads(text)
            except (ValueError, TypeError):
                documents = [{"text": documents}]
        else:
            documents = [{"text": documents}]
    if isinstance(documents, dict) and isinstance(documents.get("records"), list):
        documents = documents["records"]
    if documents is None and isinstance(data, dict) and isinstance(data.get("records"), list):
        documents = data["records"]
    if not isinstance(documents, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in documents:
        if isinstance(item, str):
            out.append({"text": item})
        elif isinstance(item, dict):
            text = item.get(text_field) if text_field in item else item.get("text")
            out.append({**item, "text": "" if text is None else str(text)})
    return out


class KnowledgeManager(BaseModel):
    """Manages RAG backends (types) and named knowledge bases (corpora)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: Optional[str] = Field(default=None, description="Directory holding knowledge bases.")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._backends: Dict[str, RagBackend] = {}

    async def initialize(self, knowledge_names: Optional[List[str]] = None,
                         base_dir: Optional[str] = None) -> None:
        """Build RAG-type backends from the KNOWLEDGE registry.

        ``base_dir`` overrides where knowledge bases are stored; without it they
        follow ``config.log_root``, which a bound session repoints at its own
        directory.
        """
        import autogenesis.knowledge  # noqa: F401 — ensure default rankers register

        self.base_dir = assemble_workspace_path(
            base_dir or self.base_dir or os.path.join(config.log_root, "knowledge"))
        for cls in list(KNOWLEDGE._module_dict.values()):
            try:
                instance: RagBackend = cls()
                if not instance.name:
                    instance.name = inflection.underscore(cls.__name__)
                self._backends[instance.name] = instance
                logger.info(f"| 📚 Registered RAG type: {instance.name}")
            except Exception as e:  # noqa: BLE001
                logger.error(f"| ❌ Failed to init RAG type {cls.__name__}: {e}")
        logger.info("| ✅ Knowledge manager initialization completed")

    async def list(self) -> List[str]:
        """The callable operations (for step validation)."""
        return list(KNOWLEDGE_OPERATIONS.keys())

    async def list_types(self) -> List[str]:
        """The available RAG retrieval types (for the node's ``type`` param)."""
        return list(self._backends.keys())

    async def get_info(self, name: str) -> Optional["_OperationInfo"]:
        description = KNOWLEDGE_OPERATIONS.get(name)
        return _OperationInfo(name=name, description=description) if description else None

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        return None

    def _base_path(self, base: str) -> str:
        safe = _SAFE_NAME.sub("_", str(base or "").strip()).strip("_") or "default"
        return os.path.join(self.base_dir or ".", safe)

    def _read_corpus(self, base: str) -> List[Dict[str, Any]]:
        path = os.path.join(self._base_path(base), "corpus.jsonl")
        if not os.path.exists(path):
            return []
        docs: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    docs.append(json.loads(line))
        return docs

    def _read_type(self, base: str, default: str = "bm25") -> str:
        path = os.path.join(self._base_path(base), "manifest.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    return json.load(handle).get("type", default)
            except (OSError, ValueError):
                pass
        return default

    async def __call__(self, name: str, input: Dict[str, Any], ctx: KnowledgeContext = None, **kwargs) -> Response:
        payload = input or {}
        if name == "knowledge_ingest":
            return self._ingest(payload)
        if name == "knowledge_retrieve":
            return await self._retrieve(payload)
        return Response(type=ResponseType.TOOL, success=False, message=f"Unknown knowledge operation: {name}")

    def _ingest(self, payload: Dict[str, Any]) -> Response:
        base = payload.get("base") or payload.get("name")
        if not base:
            return Response(type=ResponseType.TOOL, success=False, message="knowledge_ingest: 'base' is required.")
        rag_type = str(payload.get("type") or "bm25")
        if rag_type not in self._backends:
            return Response(type=ResponseType.TOOL, success=False,
                            message=f"knowledge_ingest: unknown RAG type '{rag_type}' (have {list(self._backends)}).")
        docs = _coerce_documents(payload.get("documents"), payload.get("data"), str(payload.get("text_field") or "text"))
        directory = self._base_path(base)
        try:
            os.makedirs(directory, exist_ok=True)
            with open(os.path.join(directory, "corpus.jsonl"), "a", encoding="utf-8") as handle:
                for doc in docs:
                    handle.write(json.dumps(doc, ensure_ascii=False) + "\n")
            with open(os.path.join(directory, "manifest.json"), "w", encoding="utf-8") as handle:
                json.dump({"type": rag_type}, handle)
        except OSError as exc:
            return Response(type=ResponseType.TOOL, success=False, message=f"knowledge_ingest: write failed: {exc}")
        total = len(self._read_corpus(base))
        return Response(
            type=ResponseType.TOOL, success=True,
            message=f"Ingested {len(docs)} document(s) into '{base}' ({rag_type}); {total} total.",
            data={"base": str(base), "type": rag_type, "added": len(docs), "total": total},
        )

    async def _retrieve(self, payload: Dict[str, Any]) -> Response:
        base = payload.get("base") or payload.get("name")
        query = payload.get("query") or payload.get("task") or ""
        if not base:
            return Response(type=ResponseType.TOOL, success=False, message="knowledge_retrieve: 'base' is required.")
        if not query:
            return Response(type=ResponseType.TOOL, success=False, message="knowledge_retrieve: 'query' is required.")
        try:
            top_k = max(1, int(payload.get("top_k", 4)))
        except (TypeError, ValueError):
            top_k = 4
        docs = self._read_corpus(base)
        if not docs:
            return Response(type=ResponseType.TOOL, success=False,
                            message=f"knowledge_retrieve: base '{base}' is empty or missing.")
        rag_type = self._read_type(base)
        backend = self._backends.get(rag_type)
        if backend is None:
            return Response(type=ResponseType.TOOL, success=False, message=f"knowledge_retrieve: RAG type '{rag_type}' unavailable.")
        texts = [str(doc.get("text", "")) for doc in docs]
        try:
            hits = await backend.search(str(query), texts, top_k)
        except Exception as exc:  # noqa: BLE001 — ranking failure is a failed result
            logger.error(f"| ❌ knowledge_retrieve failed: {exc}")
            return Response(type=ResponseType.TOOL, success=False, message=f"knowledge_retrieve: {exc}")
        results = [{**docs[index], "score": score} for index, score in hits if 0 <= index < len(docs)]
        return Response(
            type=ResponseType.TOOL, success=True,
            message=f"Retrieved {len(results)} document(s) from '{base}' ({rag_type}) for the query.",
            data={"base": str(base), "type": rag_type, "query": str(query), "records": results, "count": len(results)},
        )

    async def cleanup(self) -> None:
        self._backends.clear()


class _OperationInfo(BaseModel):
    name: str
    description: str = ""


knowledge_manager = KnowledgeManager()
