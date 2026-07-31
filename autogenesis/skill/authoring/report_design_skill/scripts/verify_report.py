#!/usr/bin/env python3
"""Verify that an analysis report actually EMBEDS its figures instead of just listing them.

Usage:
    python verify_report.py <path-to-report.md-or-.html>

Checks, for a report and the image files sitting next to it:
  1. Every image file in the report's directory is embedded in the report
     (markdown ``![alt](file)`` or HTML ``<img src="file">``) — not merely named in text.
  2. Every embedded *relative* image path resolves to a real, non-empty file.
  3. The malformed ``!(file.png)`` mistake (missing square brackets — renders nothing)
     does not appear.

Exits 0 if the report is a properly embedded, self-contained document; non-zero otherwise,
printing exactly what to fix. Standalone: only uses the Python standard library.
"""
import os
import re
import sys

IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")

MD_IMG = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)")               # ![alt](path)
HTML_IMG = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*['\"]([^'\"]+)", re.I)
DATA_URI_IMG = re.compile(r"(?:!\[[^\]]*\]\(|<img\b[^>]*?\bsrc\s*=\s*['\"])\s*data:image/", re.I)
MALFORMED = re.compile(r"(?<!\])!\((\s*[^)]*?\.(?:png|jpe?g|gif|svg|webp))\s*\)", re.I)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python verify_report.py <report.md|report.html>", file=sys.stderr)
        return 2

    report = os.path.abspath(sys.argv[1])
    if not os.path.isfile(report):
        print(f"❌ report not found: {report}", file=sys.stderr)
        return 2

    text = open(report, encoding="utf-8", errors="replace").read()
    report_dir = os.path.dirname(report)
    report_name = os.path.basename(report)

    # Image files sitting next to the report (candidate figures the report should embed).
    dir_images = sorted(
        f for f in os.listdir(report_dir)
        if f.lower().endswith(IMG_EXTS) and os.path.isfile(os.path.join(report_dir, f))
    )

    # Paths embedded via markdown or <img>.
    embedded_paths = set(MD_IMG.findall(text)) | set(HTML_IMG.findall(text))
    embedded_basenames = {os.path.basename(p) for p in embedded_paths}
    n_data_uri = len(DATA_URI_IMG.findall(text))
    malformed = MALFORMED.findall(text)

    problems = []

    # 1. every figure next to the report is embedded (by name, or plausibly as a data URI)
    not_embedded = [f for f in dir_images if f not in embedded_basenames]
    if not_embedded and n_data_uri < len(dir_images):
        problems.append(
            "these figures exist next to the report but are NOT embedded "
            "(list them with ![](file) / <img>, do not merely name them):\n    "
            + "\n    ".join(not_embedded)
        )

    # 2. embedded relative paths resolve to a real non-empty file
    for p in sorted(embedded_paths):
        if p.startswith(("http://", "https://", "data:")):
            continue
        abspath = p if os.path.isabs(p) else os.path.join(report_dir, p)
        if not os.path.isfile(abspath):
            problems.append(f"embedded image path does not resolve: {p}")
        elif os.path.getsize(abspath) == 0:
            problems.append(f"embedded image is empty (0 bytes): {p}")

    # 3. malformed !(...) missing the square brackets
    if malformed:
        problems.append(
            "malformed image syntax `!(...)` (missing [] — renders nothing); use ![alt](file):\n    "
            + "\n    ".join(malformed)
        )

    n_embeds = len(embedded_paths) + n_data_uri
    print(f"report: {report_name}")
    print(f"  figures in directory : {len(dir_images)}")
    print(f"  embedded images      : {len(embedded_paths)} by path + {n_data_uri} data-URI")

    if problems:
        print("\n❌ FAIL — fix the following:")
        for pr in problems:
            print(f"  - {pr}")
        return 1

    if n_embeds == 0 and dir_images:
        print("\n❌ FAIL — report embeds no images but figures exist next to it.")
        return 1

    print("\n✅ PASS — figures are embedded and resolve; report is a self-contained document.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
