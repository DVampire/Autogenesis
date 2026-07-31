---
name: data
description: "Contains dataset adapters used by the Benchmark module, including AIME, GPQA, GSM8K, LeetCode, HLE, DeepWeb, and ProgramBench."
version: 1.0.0
type: module
category: data
requirements: []
metadata: {}
---
# Data

Contains dataset adapters used by the Benchmark module, including AIME, GPQA, GSM8K,
LeetCode, HLE, DeepWeb, and ProgramBench.

Each adapter is responsible for loading its source representation and exposing normalized
examples. Evaluation policy and benchmark execution remain in `benchmark/`; generated
outputs should not be stored in this package directory.
