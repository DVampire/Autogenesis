"""One canonical capability schema with JSON and Markdown projections."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, Optional, Protocol, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

CAPABILITY_SCHEMA_VERSION = "1.0.0"


class SchemaFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "md"


class SchemaSource(str, Enum):
    DECLARED = "declared"
    INFERRED = "inferred"
    REMOTE = "remote"
    LEGACY_FALLBACK = "legacy_fallback"


class CapabilitySchemaProvider(Protocol):
    """Structural interface implemented by every callable capability Manager."""

    async def get_schema(
        self,
        name: str,
        action: Optional[str] = None,
        format: Union[str, SchemaFormat] = SchemaFormat.JSON,
    ) -> Optional[Union[Dict[str, Any], str]]:
        ...


def strict_empty_object() -> Dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": False}


class CapabilitySchema(BaseModel):
    """Internal schema contract; managers render it instead of hand-building functions."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    parameters: Dict[str, Any] = Field(default_factory=strict_empty_object)
    strict: bool = True
    source: SchemaSource = SchemaSource.DECLARED

    @model_validator(mode="after")
    def validate_parameter_contract(self):
        """Catch malformed manager schemas before they reach a model provider."""
        if self.parameters.get("type") != "object":
            raise ValueError("Function parameters schema must have type='object'")
        properties = self.parameters.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError("Function parameters.properties must be an object")
        required = self.parameters.get("required", [])
        if not isinstance(required, list) or any(item not in properties for item in required):
            raise ValueError("Function parameters.required must reference declared properties")
        if self.strict and self.parameters.get("additionalProperties") is not False:
            raise ValueError("Strict schemas must set additionalProperties=false")
        return self

    def as_function_calling(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description or self.name,
                "parameters": self.parameters,
            },
        }

    def render(self, format: Union[str, SchemaFormat] = SchemaFormat.JSON) -> Union[Dict[str, Any], str]:
        normalized = str(format.value if isinstance(format, SchemaFormat) else format).lower()
        if normalized == "json":
            return self.as_function_calling()
        if normalized in {"md", "markdown", "text"}:
            mode = "strict" if self.strict else "permissive"
            return (
                f"## `{self.name}`\n\n{self.description or self.name}\n\n"
                f"- **Schema source**: `{self.source.value}`\n"
                f"- **Validation**: `{mode}`\n\n"
                f"### Parameters\n\n```json\n"
                f"{json.dumps(self.parameters, indent=2, ensure_ascii=False)}\n```"
            )
        raise ValueError("Schema format must be 'json' or 'md'")


__all__ = [
    "CAPABILITY_SCHEMA_VERSION", "CapabilitySchema", "CapabilitySchemaProvider",
    "SchemaFormat", "SchemaSource", "strict_empty_object",
]
