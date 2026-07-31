import hashlib
import re


def render_capability_card(name: str, description: str = "", body: str = "", meta: str = "") -> str:
    """Render one tool/skill/connector as a compact markdown "card" for prompt injection.

    Layout (rendered by the message viewer's markdown + `prompt.css` card styling):

        ## <name>
        <description>  ·  <meta>

        <body>

    The `name` is the *only* heading (an H2 card header — the CSS turns it into a
    ruled divider so consecutive capabilities read as separate cards). Any markdown
    headings inside `body` (e.g. a tool's `## Parameters` / `## Example`) are
    downgraded to bold labels so they render as tight sub-sections instead of
    oversized headers. Blank lines inside `body` are collapsed to keep it compact.
    """
    header_line = f"## {name.strip()}"
    subtitle = description.strip()
    if meta.strip():
        subtitle = f"{subtitle}  ·  {meta.strip()}" if subtitle else meta.strip()

    body = (body or "").strip()
    if body:
        # Downgrade any markdown headings (#..######) to bold inline labels.
        body = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", r"**\1**", body)
        # Collapse runs of blank lines to a single blank line.
        body = re.sub(r"\n{3,}", "\n\n", body)

    lines = [header_line]
    if subtitle:
        lines.append(subtitle)
    parts = ["\n".join(lines)]
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def hash_text_sha256(text: str) -> str:
    hash_object = hashlib.sha256(text.encode())
    return hash_object.hexdigest()

def extract_boxed_content(text: str) -> str:
    """
    Extracts answers in \\boxed{}.
    """
    depth = 0
    start_pos = text.rfind(r"\boxed{")
    end_pos = -1
    if start_pos != -1:
        content = text[start_pos + len(r"\boxed{") :]
        for i, char in enumerate(content):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

            if depth == -1:  # exit
                end_pos = i
                break

    if end_pos != -1:
        return content[:end_pos].strip()

    return "None"

def dedent(text: str) -> str:
    """
    Dedent the text and expand the tabs.
    """
    clean = "\n".join(line.strip() for line in text.splitlines())
    return clean

def is_same(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()

__all__ = [
    "render_capability_card",
    "hash_text_sha256",
    "extract_boxed_content",
    "dedent",
    "is_same",
]