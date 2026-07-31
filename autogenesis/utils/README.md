---
name: utils
description: "Contains dependency-light helpers shared across modules: path assembly, file locking, concurrency, names, strings, URLs, screenshots, tokens, argument parsing, and plan models."
version: 1.0.0
type: module
category: utils
requirements: []
metadata: {}
---
# Utils

Contains dependency-light helpers shared across modules: path assembly, file locking,
concurrency, names, strings, URLs, screenshots, tokens, argument parsing, and plan models.

Utilities should be stateless or narrowly scoped. Domain behavior and Manager lifecycle
logic belong in the owning module; new helpers should not create hidden global registries.

The stable convenience exports are listed in `__init__.py`. Import a specialized helper from
its source module when it is intentionally not part of that public surface.
