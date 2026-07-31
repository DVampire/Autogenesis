"""Shared base for the AssemblyAI provider tools (ported from Langflow).

Every component sets ``aai.settings.api_key`` then uses the ``assemblyai`` SDK.
Key resolves from the arg, ``assemblyai_plugin`` config, or ``ASSEMBLYAI_API_KEY``.
"""

from __future__ import annotations

from autogenesis.plugins.types import PluginTool


class AssemblyaiToolBase(PluginTool):
    """Base for AssemblyAI tools — configure the SDK api key."""

    category: str = "data"

    def _aai(self, api_key: str = ""):
        """Import the SDK and set the api key; returns the module (or raises)."""
        key = self._secret(api_key, "ASSEMBLYAI_API_KEY")
        if not key:
            raise ValueError("no API key (set api_key or ASSEMBLYAI_API_KEY).")
        import assemblyai as aai

        aai.settings.api_key = key
        return aai
