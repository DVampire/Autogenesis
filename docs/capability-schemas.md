# Capability schemas

All callable capability Managers implement:

```python
await manager.get_schema(name, action=None, format="json")
await manager.get_schema(name, action=None, format="md")
```

This contract is formalized by the structural `CapabilitySchemaProvider` protocol, so
new Manager types can participate without inheriting a shared implementation class.

JSON is the canonical native function object. Markdown is its readable representation.
`function_callings()` delegates to `get_schema(format="json")`, so parameter contracts
have one source of truth and are not duplicated in prompts.

| Capability | Schema source |
|---|---|
| Tool | Inferred from `__call__` signature |
| Agent | Declared uniform delegation contract |
| Skill | `input_schema` in SKILL.md frontmatter; strict empty object by default |
| Connector | MCP `inputSchema` / declared `action_schemas` |
| Environment | Action function schema or Pydantic `args_schema` |
| Workflow | `<input>` attributes or sibling `<schema for="input-name">` JSON Schema |

Complex Workflow input example:

```html
<inputs>
  <input name="files" required="true" />
  <schema for="files">
    {"type":"array","items":{"type":"string"},"minItems":1}
  </schema>
</inputs>
```

The sibling form is required because `<input>` is an HTML void element. Schema JSON is
parsed as data and never executed.

Legacy Connector/Environment declarations without schemas remain permissive and are marked
`legacy_fallback` in Markdown inspection. New or updated capabilities should provide a
complete schema; strict schemas require `type=object`, valid `properties`/`required`, and
`additionalProperties=false`.
