---
name: capability
description: "Every callable Manager exposes `get_schema(name, action=None, format=\"json\")`. Managers structurally implement the typed `CapabilitySchemaProvider` protocol. `format=\"json\"` returns the exact native function-calling object consumed by `function_callings()`; `format=\"md\"` returns a human-readable contract including schema source and strict/permissive status. `CapabilitySchema` validates the shared invariants."
version: 1.0.0
type: module
category: capability
requirements: []
metadata: {}
---
# Capability schema protocol

Every callable Manager exposes `get_schema(name, action=None, format="json")`.
Managers structurally implement the typed `CapabilitySchemaProvider` protocol.
`format="json"` returns the exact native function-calling object consumed by
`function_callings()`; `format="md"` returns a human-readable contract including schema
source and strict/permissive status. `CapabilitySchema` validates the shared invariants.

Prompt context remains a compact discovery roster. Native schemas are sent separately in
the model request, and `inspect_*` tools expose both Markdown and JSON on demand.

Schema sources are `declared`, `inferred`, `remote`, and `legacy_fallback`. A legacy
fallback is intentionally permissive for backward compatibility and must not be described
as a complete contract; new built-ins should always be declared or inferred.
