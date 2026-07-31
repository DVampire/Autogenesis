---
name: init_skill
description: Initialize a new CLAUDE.md file documenting the codebase. Use when asked to create or improve a CLAUDE.md / agent-guidance file that future agent instances will read to operate in this repository.
version: 1.0.0
type: worker
license: N/A
category: workflow
requirements: [cpu]
metadata: {}
---

# Init Skill

Please analyze this codebase and create a CLAUDE.md file, which will be given to future agent instances to operate in this repository.

## What to add

1. Commands that will be commonly used, such as how to build, lint, and run tests. Include the necessary commands to develop in this codebase, such as how to run a single test.
2. High-level code architecture and structure so that future instances can be productive more quickly. Focus on the "big picture" architecture that requires reading multiple files to understand.

## Usage notes

- If there's already a CLAUDE.md, suggest improvements to it.
- When you make the initial CLAUDE.md, do not repeat yourself and do not include obvious instructions like "Provide helpful error messages to users", "Write unit tests for all new utilities", "Never include sensitive information (API keys, tokens) in code or commits".
- Avoid listing every component or file structure that can be easily discovered.
- Don't include generic development practices.
- If there are Cursor rules (in `.cursor/rules/` or `.cursorrules`) or Copilot rules (in `.github/copilot-instructions.md`), make sure to include the important parts.
- If there is a README.md, make sure to include the important parts.
- Do not make up information such as "Common Development Tasks", "Tips for Development", "Support and Documentation" unless this is expressly included in other files that you read.
- Be sure to prefix the file with the following text:

```
# CLAUDE.md

This file provides guidance to future agent instances when working with code in this repository.
```

## Tools & finish

Use `read_file_tool` / `glob_search_tool` / `grep_search_tool` to analyze the
codebase and `write_file_tool` to create `CLAUDE.md`. When done, call `done_tool`
(`result` = the path written and a one-line summary of what you documented).
