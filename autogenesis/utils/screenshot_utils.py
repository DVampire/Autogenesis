"""Screenshot storage and annotation utilities."""

import io
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw

try:
    import cairosvg
    _CAIROSVG = True
except ImportError:
    _CAIROSVG = False


class ScreenshotService:
    """Saves screenshots to disk and annotates them with cursors/paths/scrolls."""

    def __init__(self, base_dir: Union[str, Path]):
        self.base_dir = Path(base_dir)
        # Created lazily by store_screenshot — constructing the service (which happens
        # when the browser environment initializes) must not leave an empty directory.
        self.screenshots_dir = self.base_dir / "screenshots"

    async def store_screenshot(
        self,
        img: Image.Image,
        step_number: Optional[int] = None,
        screenshot_filename: Optional[str] = None,
    ) -> str:
        filename = screenshot_filename or f"step_{step_number:04d}.png"
        path = self.screenshots_dir / filename
        # filename may include a per-session subdir (e.g. "<session_id>/step_0001.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        return str(path)

    async def get_screenshot(self, screenshot_path: str) -> Optional[Image.Image]:
        path = Path(screenshot_path)
        return Image.open(path) if path.exists() else None

    async def draw_cursor(self, img: Image.Image, x: int, y: int, size: int = 32) -> Image.Image:
        if _CAIROSVG:
            svg = f'''
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 32" width="{size}" height="{size}">
                <defs>
                    <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
                        <feDropShadow dx="2" dy="2" stdDeviation="1" flood-color="rgba(0,0,0,0.3)"/>
                    </filter>
                </defs>
                <path d="M0,0 L0,26 L6,20 L11,32 L14,31 L9,19 L18,19 Z"
                      fill="black" stroke="white" stroke-width="1.2" filter="url(#shadow)"/>
            </svg>'''
            cursor_img = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode())))
            cx = max(0, min(x - size // 2, img.width - size))
            cy = max(0, min(y - size // 2, img.height - size))
            if cursor_img.mode == "RGBA":
                img.paste(cursor_img, (cx, cy), cursor_img)
            else:
                img.paste(cursor_img, (cx, cy))
        else:
            # Fallback: simple red circle
            draw = ImageDraw.Draw(img)
            r = size // 2
            draw.ellipse([x - r, y - r, x + r, y + r], outline=(255, 0, 0), width=3)
            draw.line([x - r, y, x + r, y], fill=(255, 0, 0), width=2)
            draw.line([x, y - r, x, y + r], fill=(255, 0, 0), width=2)
        return img

    async def draw_scroll(
        self, img: Image.Image, x: int, y: int, scroll_x: int, scroll_y: int
    ) -> Image.Image:
        draw = ImageDraw.Draw(img)
        magnitude = math.sqrt(scroll_x ** 2 + scroll_y ** 2)
        if magnitude == 0:
            return img
        dx, dy = scroll_x / magnitude, scroll_y / magnitude
        angle = math.degrees(math.atan2(dy, dx))

        r = 20
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(0, 0, 255, 100), outline=(0, 0, 255), width=3)
        await self._draw_arrow(draw, x, y, angle, 30)

        end_x = int(x + dx * min(magnitude, 100))
        end_y = int(y + dy * min(magnitude, 100))
        draw.line([x, y, end_x, end_y], fill=(0, 0, 255), width=4)

        label = f"Scroll: {scroll_x:+d}, {scroll_y:+d}"
        bbox = draw.textbbox((0, 0), label)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx, ty = x + r + 10, y - th // 2
        draw.rectangle([tx - 5, ty - 2, tx + tw + 5, ty + th + 2], fill=(255, 255, 255), outline=(0, 0, 0))
        draw.text((tx, ty), label, fill=(0, 0, 0))
        return img

    async def draw_path(self, img: Image.Image, path: List[List[int]], arrow_size: int = 16) -> Image.Image:
        draw = ImageDraw.Draw(img)
        if len(path) < 2:
            return img
        for i in range(len(path) - 1):
            s, e = path[i], path[i + 1]
            draw.line([s[0], s[1], e[0], e[1]], fill=(255, 0, 0), width=3)
            mid_x, mid_y = (s[0] + e[0]) // 2, (s[1] + e[1]) // 2
            dx, dy = e[0] - s[0], e[1] - s[1]
            dist = math.sqrt(dx ** 2 + dy ** 2)
            if dist > 0:
                await self._draw_arrow(draw, mid_x, mid_y, math.degrees(math.atan2(dy / dist, dx / dist)), arrow_size)
        for i, (px, py) in enumerate(path):
            r = 8
            draw.ellipse([px - r, py - r, px + r, py + r], fill=(0, 255, 0), outline=(0, 0, 0), width=2)
            label = str(i + 1)
            bbox = draw.textbbox((0, 0), label)
            draw.text((px - (bbox[2] - bbox[0]) // 2, py - (bbox[3] - bbox[1]) // 2), label, fill=(255, 255, 255))
        return img

    async def draw_som(self, img: Image.Image, elements: List[Dict[str, Any]]) -> Image.Image:
        """Draw set-of-mark boxes: a numbered bounding box per in-viewport element.

        Each element dict needs: index, left, top, width, height, in_viewport.
        """
        draw = ImageDraw.Draw(img)
        colors = [
            (229, 57, 53), (30, 136, 229), (67, 160, 71), (251, 140, 0),
            (142, 36, 170), (0, 137, 123), (216, 27, 96), (93, 64, 55),
        ]
        for el in elements:
            if not el.get("in_viewport"):
                continue
            color = colors[el["index"] % len(colors)]
            left, top = el["left"], el["top"]
            right, bottom = left + el["width"], top + el["height"]
            draw.rectangle([left, top, right, bottom], outline=color, width=2)

            label = str(el["index"])
            bbox = draw.textbbox((0, 0), label)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            # Label sits above the box's top-left corner, clamped inside the image
            lx = max(0, min(left, img.width - tw - 6))
            ly = top - th - 6 if top - th - 6 >= 0 else bottom
            ly = min(ly, img.height - th - 4)
            draw.rectangle([lx, ly, lx + tw + 6, ly + th + 4], fill=color)
            draw.text((lx + 3, ly + 2), label, fill=(255, 255, 255))
        return img

    async def _draw_arrow(self, draw: ImageDraw.ImageDraw, x: int, y: int, angle: float, size: int):
        pts = [(0, 0), (-size // 2, -size // 4), (-size // 4, -size // 2), (size // 4, -size // 2), (size // 2, -size // 4)]
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        rotated = [(int(x + px * cos_a - py * sin_a), int(y + px * sin_a + py * cos_a)) for px, py in pts]
        draw.polygon(rotated, fill=(255, 0, 0), outline=(0, 0, 0))
