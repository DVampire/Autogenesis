---
name: docker
description: "Provides the Docker backend integration point through `docker_manager`."
version: 1.0.0
type: module
category: docker
requirements: []
metadata: {}
---
# Docker

Provides the Docker backend integration point through `docker_manager`.

This module is currently a scaffold. The implemented generic isolation contract lives in
`sandbox/`; Docker-specific behavior should remain an adapter to that contract rather than
creating a second execution API.
