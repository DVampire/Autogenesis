"""Split Video."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class TwelvelabsSplitVideoTool(PluginTool):
    """Split Video."""

    name: str = 'split_video'
    display_name: str = 'Split Video'
    description: str = 'Split a video into multiple clips of specified duration.'
    category: str = 'files'

    async def __call__(self, file_path: str = "", clip_length: int = 30, **kwargs) -> Response:
        import os as _os, subprocess
        if not file_path or not _os.path.exists(file_path):
            return self._fail("twelvelabs.split_video: a valid 'file_path' is required.")
        out_dir = file_path + "_clips"
        _os.makedirs(out_dir, exist_ok=True)
        try:
            subprocess.run(["ffmpeg", "-i", file_path, "-c", "copy", "-map", "0",
                            "-segment_time", str(int(clip_length)), "-f", "segment",
                            _os.path.join(out_dir, "clip_%03d.mp4")], check=True, capture_output=True)
            clips = sorted(_os.path.join(out_dir, f) for f in _os.listdir(out_dir))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"twelvelabs.split_video: {type(exc).__name__}: {exc} (needs ffmpeg).")
        return self._ok(f"Split into {len(clips)} clips.", clips=clips, count=len(clips))
