---
name: deploy_skill
description: Deploy a web service (static site / React or other SPA / FastAPI or other API) into an isolated sandbox and get a live, reachable URL — then verify it actually serves. Use whenever a task asks to deploy, host, publish, serve, or "put online" a website or web service, or to get a shareable URL for a built app. Drives the deploy_tool end to end (pick runtime → build → deploy → verify the URL → report), manages multiple sites, and recovers from failures via logs + redeploy.
version: 1.0.0
type: worker
license: N/A
category: workflow
requirements: [cpu]
metadata: {}
---

# Deploy Skill

**Deploying here means: run a web service inside an isolated sandbox container and
bind it to a reachable URL** — one container per site, many sites side by side, each
with its own URL. You do this through the **`deploy_tool`**; this skill is the
end-to-end procedure around it: choose the right runtime, get the source built, call
`deploy_tool`, then **prove the URL actually serves** before reporting done.

This is *not* rendering a static HTML artifact (that's `artifact_design_skill`) and
*not* just running a dev server locally to test (that's `run_skill` /
`webapp_testing_skill`). Use this when the deliverable is a **running service at a
URL**.

## Backend (automatic)

`deploy_tool` picks its backend automatically: it uses the isolated **opensandbox**
(Docker) sandbox when a container runtime is available, and otherwise **falls back to
running the service directly on the host** (no container isolation) so deploys still
work on a plain machine. You can force it with the `DEPLOY_BACKEND` env var
(`sandbox` | `host` | `auto`). On the host backend, give each concurrent site a distinct
port. Either way you get a reachable URL; verify it hands-on (Step 4).

## Step 1 — Pick the runtime

Choose the `deploy_tool` `runtime` that matches the app:

| App | `runtime` | What it does |
|---|---|---|
| Plain HTML/CSS/JS, or an **already-built** SPA (a `dist/`/`build/` folder) | `static` | serves the directory over HTTP |
| React / Vue / Vite / CRA **source** (has `package.json`) | `node` | `npm ci && npm run build`, then serves the built bundle |
| FastAPI / Flask / any ASGI app | `python` | installs `requirements.txt`, runs `uvicorn` |
| Anything else (Go binary, Streamlit, custom server, bespoke image) | `custom` | you supply `image` / `build` / `start` via `overrides` |
| LLM inference service | `llm` | **not implemented yet** — use `custom` if you must |

Rule of thumb: if a build is needed, prefer building **inside** the container (`node`
/ `python` profiles do this) rather than pre-building on the host.

## Step 2 — Prepare the source

`deploy_tool` gets code into the container one of two ways:
- **`source_dir`**: an absolute host directory, uploaded into the container (good for
  files you just wrote; `node_modules`/`.git`/`dist`/`build` are skipped on upload).
- **`git_url`**: a repo cloned inside the container (good for existing projects; needs
  network).

Make sure the project is self-contained: a `node` app needs `package.json` (+ a
working `build` script); a `python` app needs `requirements.txt` and an ASGI entrypoint.

## Step 3 — Deploy

Call the tool (via `kind="tool"` if you're the MetaAgent, or directly as a sub-agent):

```json
{"name": "deploy_tool", "args": {"action": "deploy", "site_id": "coffee-shop",
  "runtime": "node", "source_dir": "/abs/path/to/project", "port": 3000}}
```

**The single hard rule: the service must listen on `0.0.0.0`, not `127.0.0.1`** — a
process bound to localhost is invisible to the URL proxy and will fail health checks.
The built-in profiles already bind `0.0.0.0`; if you pass a custom `start`, do the same.

Entry-point overrides you'll commonly need:
- `python`: default entrypoint is `app:app`. For a different one, override the start
  command, e.g. `"overrides": {"start": "uvicorn main:app --host 0.0.0.0 --port 8000"}`.
- `node`: build output is auto-detected (`dist`/`build`/`out`). For dev-server mode,
  `"overrides": {"start": "npm run dev -- --host 0.0.0.0 --port 3000"}`.
- `custom`: `overrides` **must** include `start` (and usually `image`/`build`).

On success the tool returns the site's `url`. On failure it returns
`status=failed` with an `error` (and a log tail) — go to Step 5.

## Step 4 — Verify the URL actually serves

Never report "deployed" on the tool's word alone — confirm the URL responds:
- Quick check: fetch the URL (a `bash_tool` `curl -sSI <url>`, or the browser env).
- For a real UI, drive it with the **browser environment** / `webapp_testing_skill`
  (navigate to the URL, screenshot, check the expected content renders).
- For an API, hit a known route (e.g. `GET <url>/docs` for FastAPI, or a health path)
  and check the response.

The tool's own health check only confirms the port answers HTTP; **you** confirm it's
the *right* app.

## Step 5 — On failure, diagnose then redeploy

- Read the error/log tail from the deploy result; if you need more, `deploy_tool`
  `action="get"` shows the record (status, log path).
- Common causes: server bound to `127.0.0.1`; wrong entrypoint/module; missing build
  step or dependency; wrong port. Fix the source or the `start`/`build` overrides.
- Re-run `action="deploy"` with the same `site_id` (replaces it), or
  `action="redeploy"` to rebuild from the stored request.

## Managing sites

- `action="list"` — all sites with status + URL.
- `action="get"`, `site_id` — one site's full record.
- `action="stop"`, `site_id` — tear down its container (frees resources; URL goes away).
- `action="redeploy"`, `site_id` — rebuild from the stored request (URL may change).

Use distinct `site_id`s to run several sites at once; each keeps its own URL.

## Report

When done, report the **site_id and its URL** (and how you verified it). If you
deployed more than one, list each with its URL.

## Gotchas

- **`0.0.0.0` binding** is the #1 cause of a "deployed but unreachable" site.
- URLs are served by the sandbox's port proxy — reachable where that proxy is
  reachable (host/LAN), **not automatically the public internet**.
- Sandboxes have a lifetime and live in-process; a long-idle or post-restart site may
  show `detached`/`stopped` — `redeploy` brings it back (new URL likely).
- Keep secrets out of the source; pass them via the `env` arg instead.
