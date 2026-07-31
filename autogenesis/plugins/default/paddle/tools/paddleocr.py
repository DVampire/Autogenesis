"""PaddleOCR."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class PaddleocrTool(PluginTool):
    """PaddleOCR."""

    name: str = 'paddleocr'
    display_name: str = 'PaddleOCR'
    description: str = 'Use PaddleOCR for either layout-aware document parsing into Markdown or plain OCR text recognition.'

    async def __call__(self, image_path: str = "", lang: str = "en", **kwargs) -> Response:
        import os as _os
        if not image_path or not _os.path.exists(image_path):
            return self._fail("paddle.ocr: a valid 'image_path' is required.")
        try:
            from paddleocr import PaddleOCR
            ocr = PaddleOCR(use_angle_cls=True, lang=lang)
            result = ocr.ocr(image_path, cls=True)
            lines = [line[1][0] for page in (result or []) for line in (page or [])]
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"paddle.ocr: {type(exc).__name__}: {exc}")
        return self._ok(f"Extracted {len(lines)} text lines.", text="\n".join(lines), lines=lines)
