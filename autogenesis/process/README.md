---
name: process
description: "Pure record/text transforms — the transform stage of a data pipeline. A processor is a side-effect-free (input, params) -> output and returns the canonical {message, data, files} envelope so it composes with datasource, data, and benchmark nodes."
version: 1.0.0
type: module
category: process
requirements: []
metadata: {}
---
# Process

Pure transforms that sit between a `datasource` (which fetches) and a `benchmark` (which
evaluates): select/filter/sort/rename records, split/regex/parse/convert text and JSON,
DataFrame ops, and eval-record shaping. Every processor is side-effect free and returns the
canonical `{message, data, files}` envelope, dispatched through `process_manager`.
