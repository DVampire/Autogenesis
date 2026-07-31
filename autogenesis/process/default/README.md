---
name: process_default
description: "Registers the built-in processors (select_fields, filter_rows, sort_records, split_text, regex_extract, parse_json, type_convert, combine_text, extract_field, table_operations, derive_return, to_eval_records). Implementations conform to the Processor contract of the parent Process module."
version: 1.0.0
type: collection
category: process
requirements: []
metadata: {}
---
# Built-in processors

Registers the standard record/text/table transforms. Each is a pure `Processor`; new
operators drop in by registering a class.
