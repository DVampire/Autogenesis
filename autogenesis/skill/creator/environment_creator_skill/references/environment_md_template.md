---
name: my_environment
description: One line — what the environment is and when to use it.
version: 1.0.0
type: worker
---

<environment_my_environment>

## State
Describe what the environment holds/simulates and how it behaves across calls
(e.g. an in-memory key-value store; a running browser page; a game board). This is
what an agent needs to understand before acting.

## Vision
(Include this section ONLY if some action returns an image.) Say what the visual
output is (e.g. "a base64 PNG screenshot of the rendered page") and how the agent
should use it (inspect it, then iterate).

## Actions

### set_value
Store a value under a key. Args: `key` (str), `value` (str). Use when you need to
remember something for a later step.

### get_value
Read the value stored under a key. Args: `key` (str). Returns the value or null if
unset.
