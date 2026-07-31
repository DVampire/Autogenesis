"""SnapshotHook — persists each think-and-act step's rendered messages as an HTML file.

The message content IS the prompt with its fields filled in (the prompt templates
are authored in HTML with `<profile>`, `<project>`, `<task>`, ... tags). So each
snapshot simply re-emits that content verbatim inside `div.system` / `div.user`
wrappers and links the SAME `prompt.css` / `prompt.js` the prompt templates use —
i.e. it renders identically to the live prompt, no re-styling.

On every POST_STEP the step's messages are written to:

    <log_root>/messages/<agent_name>/<NNNN>.html   (0001.html, 0002.html, ...)
"""
import os
from html import escape as _he

from autogenesis.hook.types import Hook, HookContext, HookEvent, HookResult
from autogenesis.registry import HOOK
from autogenesis.visual import css_path, js_path
from autogenesis.logger import logger


def _msg_text(m) -> str:
    """The message's content (already HTML — the filled prompt), verbatim."""
    txt = getattr(m, "text", None)
    if isinstance(txt, str):
        return txt
    content = getattr(m, "content", m)
    return content if isinstance(content, str) else str(content)


@HOOK.register_module(force=True)
class SnapshotHook(Hook):
    """Writes a per-step HTML snapshot of the rendered messages after each step."""

    name: str = "snapshot_hook"
    description: str = "Saves each think-and-act step's rendered messages as HTML (rendered with prompt.css/js)."
    events: list = []
    priority: int = 90  # run late; it only observes

    async def handle(self, ctx: HookContext) -> HookResult:
        """On POST_STEP, write the step's rendered messages to a numbered HTML file.

        Ignores non-POST_STEP events and empty message lists. Otherwise renders
        the messages verbatim (they are already filled-in prompt HTML) into
        ``<log_root>/messages/<agent_name>/<NNNN>.html``. Purely observational —
        any I/O error is logged and swallowed.

        Args:
            ctx: Hook context whose ``input`` carries ``event``, ``messages``,
                ``agent_name`` and ``step_number``.

        Returns:
            Always ``HookResult.allow()``.
        """
        inp = ctx.input or {}
        if inp.get("event") != HookEvent.POST_STEP:
            return HookResult.allow()

        messages = inp.get("messages")
        if not messages:
            return HookResult.allow()

        agent_name = inp.get("agent_name") or "agent"
        step_number = int(inp.get("step_number") or 0)

        try:
            from autogenesis.config import config
            base_dir = str(getattr(config, "log_root", None) or inp.get("workspace_root") or ".")
            out_dir = os.path.join(base_dir, "messages", agent_name)
            os.makedirs(out_dir, exist_ok=True)
            file_path = os.path.join(out_dir, f"{step_number + 1:04d}.html")

            html = self._render(file_path, agent_name, step_number, messages)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.debug(f"| 📸 SnapshotHook: wrote {file_path}")
        except Exception as e:
            logger.debug(f"| SnapshotHook failed: {e}")

        return HookResult.allow()

    def _render(self, file_path, agent_name, step_number, messages) -> str:
        """Build the standalone HTML snapshot for one step's messages.

        Links the same ``prompt.css``/``prompt.js`` assets (via paths relative to
        ``file_path``) that the prompt templates use, then re-emits each message's
        content inside ``div.system``/``div.user`` wrappers so the snapshot renders
        identically to the live prompt.

        Returns:
            The complete HTML document as a string.
        """
        # Link the SAME assets the prompt templates use, so the filled prompt
        # renders exactly like the live prompt.
        d = os.path.dirname(file_path)
        css_rel = os.path.relpath(css_path("prompt.css"), start=d)
        js_rel = os.path.relpath(js_path("prompt.js"), start=d)
        parts = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="UTF-8">',
            f"  <title>{_he(agent_name)} — step {step_number + 1:04d}</title>",
            f'  <link rel="stylesheet" href="{_he(css_rel)}">',
            f'  <script src="{_he(js_rel)}"></script>',
            "</head>",
            "<body>",
        ]
        # Re-emit each message's content verbatim in the prompt's own wrappers.
        for m in messages:
            role = str(getattr(m, "role", "user"))
            cls = "system" if role == "system" else "user"
            parts.append(f'<div class="{cls}">')
            parts.append(_msg_text(m))
            parts.append("</div>")
        parts += ["</body>", "</html>"]
        return "\n".join(parts)
