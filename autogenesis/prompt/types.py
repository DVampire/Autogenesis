"""Prompt Context Protocol (PCP) Types

Core type definitions for the Prompt Context Protocol.
Prompts are loaded from .html files; each file defines one agent prompt (system + user).
"""
import os
import re
from html.parser import HTMLParser
from typing import Any, Dict, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field, ConfigDict, PrivateAttr

from autogenesis.logger import logger
from autogenesis.message import Message, SystemMessage, HumanMessage, ContentPartText
from autogenesis.session import BaseContext


try:
    from jinja2 import Template as JinjaTemplate
    _JINJA2_AVAILABLE = True
except ImportError:
    _JINJA2_AVAILABLE = False


def _render_template(template_str: str, modules: Dict[str, Any]) -> str:
    if not _JINJA2_AVAILABLE:
        return template_str
    return JinjaTemplate(template_str).render(**modules)


class _PromptHTMLParser(HTMLParser):
    """SAX-style parser that extracts meta attributes and div.system/div.user contents."""

    def __init__(self):
        super().__init__()
        self.meta: Dict[str, str] = {}
        self._in_section: Optional[str] = None
        self._depth: int = 0  # nesting depth inside the top-level section div
        self._buf: list = []
        self.sections: Dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == "meta":
            name = attr_dict.get("name", "")
            content = attr_dict.get("content", "")
            if name:
                self.meta[name] = content
            return

        if tag == "div" and self._in_section is None:
            cls = attr_dict.get("class", "")
            if cls in ("system", "user"):
                self._in_section = cls
                self._depth = 1
                self._buf = []
                return

        if self._in_section is not None:
            # Reconstruct opening tag verbatim so inner HTML is preserved
            attrs_str = ""
            for k, v in attrs:
                attrs_str += f' {k}="{v}"' if v is not None else f' {k}'
            self._buf.append(f"<{tag}{attrs_str}>")
            if tag == "div":
                self._depth += 1

    def handle_endtag(self, tag):
        if self._in_section is None:
            return
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.sections[self._in_section] = "".join(self._buf).strip()
                self._in_section = None
                return
            # inner closing div — write to buf and fall through
        self._buf.append(f"</{tag}>")

    def handle_data(self, data):
        if self._in_section is not None:
            self._buf.append(data)

    def handle_entityref(self, name):
        if self._in_section is not None:
            self._buf.append(f"&{name};")

    def handle_charref(self, name):
        if self._in_section is not None:
            self._buf.append(f"&#{name};")


# Matches a full <module ... src="..."></module> pluggable-slot element (any attribute order).
_MODULE_RE = re.compile(
    r'<module\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\'][^>]*>\s*</module>',
    re.IGNORECASE | re.DOTALL,
)
# Captures the inner content of a module file's <body>...</body>.
_BODY_RE = re.compile(r'<body[^>]*>(.*)</body>', re.IGNORECASE | re.DOTALL)


def _module_body(path: str) -> str:
    """Read a pluggable module file and return the inner HTML of its <body> (stripped).

    The module's <head> (its own CSS/JS <link>/<script>, used only for browser preview)
    is intentionally dropped so it never leaks into the rendered message.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    m = _BODY_RE.search(text)
    return (m.group(1) if m else text).strip()


def expand_modules(section_html: str, base_dir: str, _depth: int = 0) -> str:
    """Inline every ``<module src="...">`` slot with the referenced module's <body> content.

    This is the server-side half of the pluggable-module mechanism. In the browser
    ``visual/js/prompt.js`` fetches the same ``<module>`` slot and injects the module's body
    inline so prompt.css/js styles it as a native block; here we splice the body text in
    place of the slot so the model never sees a literal tag.

    ``src`` is resolved relative to ``base_dir`` (the prompt file's directory). A module may
    itself contain module slots; those resolve relative to the module's own directory.
    """
    if _depth > 10:
        raise ValueError("module expansion exceeded max depth (possible cycle)")

    def _replace(match: "re.Match") -> str:
        src = match.group(1)
        module_path = os.path.normpath(os.path.join(base_dir, src))
        body = _module_body(module_path)
        return expand_modules(body, os.path.dirname(module_path), _depth + 1)

    return _MODULE_RE.sub(_replace, section_html)


def parse_prompt_text(text: str) -> "PromptConfig":
    """Parse a full HTML file text into a PromptConfig."""
    parser = _PromptHTMLParser()
    parser.feed(text)

    meta = parser.meta
    name = meta.get("name", "")
    description = meta.get("description", "")
    version = str(meta.get("version", "1.0.0"))
    enable_evolving = meta.get("enable_evolving", "false").lower() == "true"

    system_template = parser.sections.get("system", "")
    user_template = parser.sections.get("user", "")

    return PromptConfig(
        name=name,
        description=description,
        version=version,
        enable_evolving=enable_evolving,
        system_template=system_template,
        user_template=user_template,
    )


def parse_prompt_file(path: str) -> "PromptConfig":
    """Read and parse an .html file into a PromptConfig."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        cfg = parse_prompt_text(text)
    except Exception as e:
        raise ValueError(f"Failed to parse html file {path}: {e}") from e
    # Inline any pluggable <module> slots, resolved relative to this file's directory.
    base_dir = os.path.dirname(os.path.abspath(path))
    cfg.system_template = expand_modules(cfg.system_template, base_dir)
    cfg.user_template = expand_modules(cfg.user_template, base_dir)
    return cfg


class Prompt(BaseModel):
    """A prompt loaded from an .md file, with system and user templates."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="Prompt name, from md frontmatter")
    description: str = Field(default="", description="Short description of the agent")
    version: str = Field(default="1.0.0", description="Version string")
    enable_evolving: bool = Field(default=False, description="Whether this prompt is a trainable variable")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    system_template: str = Field(default="", description="System prompt text (Jinja2)")
    user_template: str = Field(default="", description="User/agent message text (Jinja2)")
    variables: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Static Jinja2 render-context defaults")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Miscellaneous metadata")

    _system_message_cache: Optional[SystemMessage] = PrivateAttr(default=None)

    def _merged_modules(self, modules: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(self.variables or {})
        if modules:
            merged.update(modules)
        return merged

    async def get_system_message(self, modules: Optional[Dict[str, Any]] = None, reload: bool = False) -> SystemMessage:
        if self._system_message_cache is not None and not reload:
            return self._system_message_cache
        rendered = _render_template(self.system_template, self._merged_modules(modules))
        self._system_message_cache = SystemMessage(content=rendered)
        return self._system_message_cache

    async def get_user_message(self, modules: Optional[Dict[str, Any]] = None, reload: bool = True) -> HumanMessage:
        rendered = _render_template(self.user_template, self._merged_modules(modules))
        return HumanMessage(content=[ContentPartText(text=rendered)])

    def __str__(self):
        return f"Prompt(name={self.name}, version={self.version})"

    def __repr__(self):
        return self.__str__()


class PromptConfig(BaseModel):
    """Prompt configuration — parsed from an .md file or loaded from JSON."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="Prompt name")
    description: str = Field(default="", description="Short description")
    version: str = Field(default="1.0.0", description="Version string")
    enable_evolving: bool = Field(default=False, description="Whether the whole prompt is a trainable variable")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    system_template: str = Field(default="", description="System prompt text")
    user_template: str = Field(default="", description="User/agent message text")
    variables: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Static Jinja2 render-context defaults")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Miscellaneous metadata")

    def to_prompt(self) -> Prompt:
        return Prompt(
            name=self.name,
            description=self.description,
            version=self.version,
            enable_evolving=self.enable_evolving,
            permission_mode=self.permission_mode,
            system_template=self.system_template,
            user_template=self.user_template,
            variables=self.variables or {},
            metadata=self.metadata or {},
        )

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "enable_evolving": self.enable_evolving,
            "permission_mode": self.permission_mode,
            "system_template": self.system_template,
            "user_template": self.user_template,
            "variables": self.variables or {},
            "metadata": self.metadata or {},
        }

    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> "PromptConfig":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            enable_evolving=data.get("enable_evolving", False),
            permission_mode=data.get("permission_mode", "workspace_write"),
            system_template=data.get("system_template", ""),
            user_template=data.get("user_template", ""),
            variables=data.get("variables", {}),
            metadata=data.get("metadata", {}),
        )

    def __str__(self):
        return f"PromptConfig(name={self.name}, version={self.version})"

    def __repr__(self):
        return self.__str__()


class PromptContext(BaseContext):
    """Context passed into the prompt manager when rendering messages."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Unique identifier for this prompt render.")
    name: str = Field(default="", description="Name of the prompt being rendered.")
    workspace_root: Optional[str] = Field(default=None, description="Working directory available to the caller.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload passed to the prompt.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this prompt context.")


__all__ = [
    "Prompt",
    "PromptConfig",
    "PromptContext",
    "parse_prompt_file",
]
