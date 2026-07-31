"""FAISS."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import VectorStorePluginTool


class FaissTool(VectorStorePluginTool):
    """FAISS."""

    name: str = 'faiss'
    display_name: str = 'FAISS'
    description: str = 'FAISS Vector Store with search capabilities'

    def _build(self, embedding: Any, **conn: Any) -> Any:
        from langchain_community.vectorstores import FAISS
        folder = conn.get("folder_path") or ""
        idx = conn.get("index_name") or "langflow"
        if folder:
            import os
            if os.path.isdir(folder) and os.path.exists(os.path.join(folder, f"{idx}.faiss")):
                return FAISS.load_local(folder, embedding, index_name=idx,
                                        allow_dangerous_deserialization=True)
        # Fresh in-memory store (seed text needed before search; add_texts handles ingest).
        return FAISS.from_texts(["__init__"], embedding)

    async def __call__(self, folder_path: str = "", index_name: str = "langflow", query: str = "", texts: Optional[List[str]] = None,
                       embedding: str = "", k: int = 4, **kwargs) -> Response:
        return await self._run(query=query, texts=texts, embedding=embedding, k=int(k),
            folder_path=folder_path, index_name=index_name)
