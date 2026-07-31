"""Visual assets for Autogenesis — CSS, JS, templates, and rendering helpers."""

import os
from html import escape


def css_path(filename: str) -> str:
    """Return the absolute path to a CSS file in autogenesis/visual/css/."""
    return os.path.join(os.path.dirname(__file__), "css", filename)


def js_path(filename: str) -> str:
    """Return the absolute path to a JS file in autogenesis/visual/js/."""
    return os.path.join(os.path.dirname(__file__), "js", filename)


def render_task_page(html_body: str, out_path: str, title: str = "Task") -> str:
    """Render a task document body into a standalone, styled HTML page.

    Mirrors the prompt's page shell (meta_agent.html): metadata as ``<meta>``
    tags in ``<head>``, ``task.css`` + ``task.js`` linked there, and the body
    inserted directly (the body already carries its ``<div class="task">``
    wrapper, or a ``<div class="task-doc">`` for Markdown tasks). ``task.js``
    renders the Markdown inside the section tags client-side. Returns ``out_path``.
    """
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    css_rel = os.path.relpath(css_path("task.css"), start=out_dir)
    js_rel = os.path.relpath(js_path("task.js"), start=out_dir)
    page = "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="UTF-8">',
        f'  <meta name="description" content="{escape(title)}">',
        f'  <link rel="stylesheet" href="{escape(css_rel)}">',
        f'  <script src="{escape(js_rel)}"></script>',
        "</head>",
        "<body>",
        html_body,
        "</body>",
        "</html>",
    ])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    return out_path
