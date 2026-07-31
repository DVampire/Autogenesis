---
name: logger
description: "Provides the framework logger, log levels, display colors, and session-ID context used to correlate output across asynchronous operations."
version: 1.0.0
type: module
category: logger
requirements: []
metadata: {}
---
# Logger

Provides the framework logger, log levels, display colors, and session-ID context used to
correlate output across asynchronous operations.

The public API is exported from `log.py`. Modules should use the shared `logger` rather than
constructing independent logging configurations.
