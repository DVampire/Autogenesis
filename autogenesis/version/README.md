---
name: version
description: "Tracks versions of evolvable framework entities and generates validated next versions."
version: 1.0.0
type: module
category: version
requirements: []
metadata: {}
---
# Version

Tracks versions of evolvable framework entities and generates validated next versions.

| File | Responsibility |
|---|---|
| `types.py` | Version-related data contracts |
| `server.py` | Public `version_manager`, comparison, registration, and incrementing |

Owning Managers decide when a new entity version is promoted; Version supplies consistent
version arithmetic and history identifiers.
