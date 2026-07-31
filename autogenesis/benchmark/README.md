---
name: benchmark
description: "Provides versioned benchmark definitions and the manager used to load and execute them. Built-in benchmark adapters live in `default/`; dataset parsing belongs to `data/`."
version: 1.0.0
type: module
category: benchmark
requirements: []
metadata: {}
---
# Benchmark

Provides versioned benchmark definitions and the manager used to load and execute them.
Built-in benchmark adapters live in `default/`; dataset parsing belongs to `data/`.

| File | Responsibility |
|---|---|
| `types.py` | Benchmark and configuration contracts |
| `context.py` | Benchmark registry and lifecycle state |
| `server.py` | Public `benchmark_manager` facade |
| `utils.py` | Shared benchmark helpers |

New benchmarks should implement the base contract and register through the normal registry
instead of adding selection logic to the server.
