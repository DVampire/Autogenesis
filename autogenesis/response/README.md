---
name: response
description: "Defines the normalized `Response` and `ResponseType` returned across Agents, Tools, Skills, Connectors, and Environments."
version: 1.0.0
type: module
category: response
requirements: []
metadata: {}
---
# Response

Defines the normalized `Response` and `ResponseType` returned across Agents, Tools, Skills,
Connectors, and Environments.

Contracts live in `types.py`. Capability implementations should return this neutral form
rather than leaking provider- or transport-specific response objects.
