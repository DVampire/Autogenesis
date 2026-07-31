---
name: run_skill
description: Launch and drive this project's app to see a change working. Use when asked to run, start, or screenshot the app, or to confirm a change works in the real app (not just tests). First looks for a project skill that already covers launching the app; otherwise falls back to built-in patterns per project type (CLI, server, TUI, Electron, browser-driven, library).
version: 1.0.0
type: worker
license: N/A
category: workflow
requirements: [cpu]
metadata: {}
---

# Run Skill

**Running means launching the actual app and interacting with it** —
not the test suite, not an `import` of an internal function and a
`console.log`. The app as a user (human or programmatic) would meet
it: the CLI at its command, the server at its socket, the GUI at its
window.

## First: does a project skill already cover this?

A project skill that launches this app is the repo's verified path —
its author already cold-started from a clean container and committed
what worked: the exact `apt-get` line, the env vars, the patches, the
driver. Use it instead of rediscovering.

Scan the framework's skill directories for one whose description covers
launching this app:

```bash
grep -Hm1 '^description:' autogenesis/skill/default/*/SKILL.md extension/skill/*/SKILL.md 2>/dev/null
```

- **One describes launching/driving this app** → read that SKILL.md
  and follow it verbatim. Don't paraphrase; don't skip the patches.
- **Mega-repo, several plausible, no clear match** → ask the user
  which unit to run.
- **Stale** (fails on mechanics unrelated to your task) → tell the
  user; offer to refresh it.
- **Nothing about running** → fall back to the patterns below.

## Otherwise: match the shape, use the pattern

Pick the row closest to your project. Each handle is the smallest
launch + first interaction for that shape.

| Project type | Handle |
|---|---|
| CLI tool | direct invocation, exit code, stdin/stdout |
| Web server / API | background launch + `curl` smoke |
| TUI / interactive terminal | tmux `send-keys` / `capture-pane` |
| Electron / desktop GUI | Playwright `_electron` REPL under xvfb |
| Browser-driven | dev server + headless chromium script |
| Library / SDK | import-and-call smoke script at the package boundary |

If nothing fits, start from the closest match and adapt. For a web
app, drive it with a headless chromium script, no custom driver
needed. For a desktop app, use the `_electron` REPL driver skeleton
and the tmux wrapping.

## Drive it, don't just launch it

Launching with no interaction proves the entrypoint resolves. That's
not running the app — it's typechecking with extra steps. Drive it to
a point where a user would see something:

- CLI → type a representative command, check the exit code and output.
- Server → hit the route the diff touches with `curl`, read the body.
- TUI → `send-keys` a navigation, `capture-pane` the result.
- GUI → click the button, screenshot the window. **Look at the
  screenshot.** A blank frame is a failure to launch.

If the fallback pattern didn't work out of the box — you had to
install packages, set env vars, patch config, or write a driver —
recommend capturing that work as a project skill in your report so it
gets reused. If it just worked, don't.
