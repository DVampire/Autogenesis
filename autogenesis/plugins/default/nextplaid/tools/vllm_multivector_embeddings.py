"""vLLM Multivector Embeddings."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class NextplaidVllmMultivectorEmbeddingsTool(PluginTool):
    """vLLM Multivector Embeddings."""

    name: str = 'vllm_multivector_embeddings'
    display_name: str = 'vLLM Multivector Embeddings'
    description: str = ''
    category: str = 'knowledge'

    async def __call__(self, text: str = "", base_url: str = "http://localhost:8000/v1", model_name: str = "", api_key: str = "", **kwargs) -> Response:
        import httpx
        if not text or not base_url:
            return self._fail("nextplaid.vllm_embeddings: 'text' and 'base_url' are required.")
        try:
            resp = httpx.post(f"{base_url.rstrip('/')}/embeddings",
                              headers={"Authorization": f"Bearer {self._secret(api_key, 'VLLM_API_KEY') or 'EMPTY'}"},
                              json={"model": model_name, "input": text}, timeout=60.0)
            resp.raise_for_status()
            vec = resp.json()["data"][0]["embedding"]
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"nextplaid.vllm_embeddings: {type(exc).__name__}: {exc}")
        return self._ok(f"Embedded text ({len(vec)} dims).", vector=vec, dims=len(vec))
