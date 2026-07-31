---
name: plugins_default
description: "Registers the built-in provider plugins (Yahoo Finance, Financial Modeling Prep). Implementations conform to the Plugin contract documented by the parent Plugins module."
version: 1.0.0
type: collection
category: plugins
requirements: []
metadata: {}
---
# Built-in plugins

Registers the built-in data-source providers (`yahoo`, `fmp`). Each is a `Plugin` returning
records via the canonical `{message, data, files}` envelope; new providers drop in by
registering a class.
