"""Shared contracts for capabilities projected as native functions."""

from .schema import (
    CAPABILITY_SCHEMA_VERSION,
    CapabilitySchema,
    CapabilitySchemaProvider,
    SchemaFormat,
    SchemaSource,
    strict_empty_object,
)

__all__ = [
    "CAPABILITY_SCHEMA_VERSION", "CapabilitySchema", "CapabilitySchemaProvider",
    "SchemaFormat", "SchemaSource", "strict_empty_object",
]
