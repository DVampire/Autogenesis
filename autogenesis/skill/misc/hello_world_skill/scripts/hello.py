"""Hello World skill utility script — generate and validate greetings."""

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional


RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"


class HelloGreeter:
    """Greeting generator that loads templates from resources/greetings.json."""

    MAX_GREETING_LENGTH = 500

    def __init__(
        self,
        default_name: Optional[str] = None,
        default_style: Optional[str] = None,
        default_locale: Optional[str] = None,
        resource_path: Optional[Path] = None,
    ):
        self._resource_path = resource_path or RESOURCES_DIR / "greetings.json"
        self._data = self._load_resource()

        defaults = self._data.get("defaults", {})
        self.default_name = default_name or os.environ.get(
            "HELLO_DEFAULT_NAME", defaults.get("name", "World")
        )
        self.default_style = default_style or os.environ.get(
            "HELLO_DEFAULT_STYLE", defaults.get("style", "casual")
        )
        self.default_locale = default_locale or os.environ.get(
            "HELLO_LOCALE", defaults.get("locale", "en")
        )

    def _load_resource(self) -> dict:
        try:
            with open(self._resource_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: resource file not found at {self._resource_path}, using built-in defaults.",
                  file=sys.stderr)
            return {
                "styles": {
                    "casual": {"templates": ["Hey there, {name}! 👋 Welcome aboard!"]},
                    "formal": {"templates": ["Good day, {name}. It is a pleasure to make your acquaintance."]},
                    "festive": {"templates": ["🎉 Happy celebrations, {name}! Wishing you all the best! 🎉"]},
                },
                "locales": {"en": "Hello, {name}!"},
                "defaults": {"name": "World", "style": "casual", "locale": "en"},
            }

    @property
    def available_styles(self) -> List[str]:
        return list(self._data.get("styles", {}).keys())

    @property
    def available_locales(self) -> List[str]:
        return list(self._data.get("locales", {}).keys())

    def _pick_template(self, style: str) -> str:
        """Randomly pick one template from the style's template list."""
        style_data = self._data.get("styles", {}).get(style)
        if style_data is None:
            print(f'Warning: Unknown style "{style}". Falling back to "{self.default_style}".',
                  file=sys.stderr)
            style_data = self._data["styles"][self.default_style]
        templates = style_data.get("templates", [])
        return random.choice(templates) if templates else "Hello, {name}!"

    def generate(self, name: Optional[str] = None, style: Optional[str] = None) -> str:
        name = name or self.default_name
        style = style or self.default_style
        template = self._pick_template(style)
        return template.format(name=name)

    def generate_locale(self, name: Optional[str] = None, locale: Optional[str] = None) -> str:
        name = name or self.default_name
        locale = locale or self.default_locale
        locales = self._data.get("locales", {})
        template = locales.get(locale)
        if template is None:
            print(f'Warning: Unknown locale "{locale}". Falling back to "en".', file=sys.stderr)
            template = locales.get("en", "Hello, {name}!")
        return template.format(name=name)

    def validate(self, text: str) -> bool:
        if not text or not text.strip():
            print("Validation failed: greeting is empty.", file=sys.stderr)
            return False
        if len(text) > self.MAX_GREETING_LENGTH:
            print(f"Validation failed: greeting exceeds {self.MAX_GREETING_LENGTH} characters.",
                  file=sys.stderr)
            return False
        print("Validation passed.")
        return True

    def list_styles(self) -> None:
        for style in self.available_styles:
            templates = self._data["styles"][style]["templates"]
            preview = templates[0].format(name="<name>") if templates else "(no templates)"
            print(f"  {style:10s} — {preview}")

    def list_locales(self) -> None:
        for locale, template in self._data.get("locales", {}).items():
            print(f"  {locale:5s} — {template.format(name='<name>')}")


def main():
    parser = argparse.ArgumentParser(description="Hello World greeting generator")
    parser.add_argument("--name", default=None, help="Target name")
    parser.add_argument("--style", default=None, help="Greeting style")
    parser.add_argument("--locale", default=None, help="Greeting locale (e.g. en, zh, ja)")
    parser.add_argument("--validate", action="store_true", help="Validate a greeting")
    parser.add_argument("--input", dest="input_text", help="Text to validate")
    parser.add_argument("--list-styles", action="store_true", help="List styles")
    parser.add_argument("--list-locales", action="store_true", help="List locales")

    args = parser.parse_args()
    greeter = HelloGreeter()

    if args.list_styles:
        greeter.list_styles()
        return

    if args.list_locales:
        greeter.list_locales()
        return

    if args.validate:
        ok = greeter.validate(args.input_text or "")
        sys.exit(0 if ok else 1)

    if args.locale:
        print(greeter.generate_locale(name=args.name, locale=args.locale))
    else:
        print(greeter.generate(name=args.name, style=args.style))


if __name__ == "__main__":
    main()
