---
name: visual
description: "This directory contains dependency-free browser renderers for Autogenesis's HTML-native artifacts. Runtime parsers never execute these files; CSS and JavaScript are for human preview only."
version: 1.0.0
type: module
category: visual
requirements: []
metadata: {}
---
# Visual assets

This directory contains dependency-free browser renderers for Autogenesis's HTML-native
artifacts. Runtime parsers never execute these files; CSS and JavaScript are for human
preview only.

| Asset | Purpose |
|---|---|
| `css/prompt.css`, `js/prompt.js` | Prompt HTML preview |
| `css/workflow.css`, `js/workflow.js` | Dynamic Workflow metadata and nested execution-program preview |
| `css/task.css`, `js/task.js` | Task visualization |
| `css/memory.css` | Memory visualization |
| `css/plan.css` | Plan visualization |

The Workflow renderer reads the embedded `<workflow>` element without modifying it, so
the same complete HTML file remains valid input to `WorkflowCompiler` and a standalone
browser document.
