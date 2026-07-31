---
name: agent_creator_skill
description: Create new agents, improve/optimize existing agents (both Python class and HTML prompt), and evaluate agent quality — the full agent lifecycle in this framework. Use whenever the task involves authoring a new agent, editing/improving an existing agent or its prompt, or evaluating/scoring an agent. MetaAgent uses it to orchestrate the create→evaluate→improve loop across sub-agents.
version: 1.1.0
type: [orchestrator, worker]
category: meta
requirements: [cpu]
metadata: {}
---

# Agent Creator

A single skill for the full lifecycle of **agents**: creating new ones, improving existing ones (class *and* prompt), and evaluating their quality. An agent in this framework is a thin Python class over the shared base `Agent`, usually paired with an HTML prompt (for tool-calling agents) and a config.

At a high level, building a good agent is a loop: decide what it should do → pick the agent type → write a thin class + a focused prompt from the templates → run it on realistic tasks → evaluate → improve the prompt/class → repeat.

## How this skill is used — four roles, one body of knowledge

- **MetaAgent (orchestrator role)** — drives the create→evaluate→improve loop, dispatching the sub-agents. See **Orchestration**.
- **agent_generate_agent** — reads **Creating an agent**.
- **agent_optimize_agent** — reads **Improving an agent** (this is where most of the value is — prompt tuning).
- **agent_evaluate_agent** — reads **Evaluating an agent**.

The sub-agents are headless: each runs one phase autonomously and returns a result. There is no human-in-the-loop review.

## Reference templates — read before writing

Start from the bundled templates instead of writing from scratch:
- `references/tool_calling_agent_template.py` — a thin tool-calling agent class (the common case).
- `references/procedural_agent_template.py` — a deterministic, code-driven agent (no LLM loop, no prompt).
- `references/html_prompt_template.html` — the HTML prompt skeleton for a tool-calling agent.

Read the relevant template(s) first, copy, then adapt. They already encode the current architecture and the template-variable contract.

## Framework conventions (read once)

An agent has up to three files:
- `{extension_root}/agent/{name}.py` — the Python class (REQUIRED).
- `{extension_root}/prompt/{name}.html` — the HTML prompt (REQUIRED for tool-calling agents; procedural agents omit it).
- `{extension_root}/configs/agents/{name}.py` — the config dict.

**Registration is automatic via a hook**: after writing the files, include the Python file path in your `done_tool` reasoning — the `agent_registration_hook` locates and registers it. The class name in `done_tool` reasoning helps it resolve.

---

## Choosing the agent type

- **Tool-calling agent** (default): reasons and acts step by step, choosing tools/skills dynamically each step. Use it for open-ended or multi-step tasks. It has a Python class + an HTML prompt, and it **inherits** the base loop. → `tool_calling_agent_template.py` + `html_prompt_template.html`.
- **Procedural agent**: a fixed, deterministic pipeline (read → process → report) expressed in code with direct tool calls — no step-by-step LLM planning, no prompt. It subclasses `ProceduralAgent` and implements `run_procedure`; it never overrides `__call__`. → `procedural_agent_template.py`.

When unsure, prefer a tool-calling agent — it's the more general, more capable form.

---

## Creating an agent

### The class is THIN — inherit, don't reinvent

The base `Agent` already implements the standard think-and-act loop (`__call__`) and the context builder (`_get_agent_context`, `_get_messages`, `_think_and_act`). A well-formed tool-calling agent **inherits all of it** and only supplies:
- its identity fields (`name`, `description`, `metadata`, `enable_evolving`),
- an `__init__` that sets `prompt_name` (must match the HTML prompt's `<meta name="name">`),
- a thin `__call__` that delegates to `super().__call__(...)`.

**Do NOT override** `_get_agent_context`, `_get_messages`, or `_think_and_act` unless the agent genuinely needs bespoke behavior — reviewers treat unnecessary overrides as a defect. The only common reason to put real logic in `__call__` is an agent that must **register a produced artifact**: it calls `super().__call__(...)`, then fires a registration hook on the result (see the variant in `tool_calling_agent_template.py`).

Steps:
1. Read `tool_calling_agent_template.py`, copy it to `extension/agent/{name}.py`, rename the class, and fill `name` / `description` (state what it does AND when to use it) / `prompt_name`.
2. Write the HTML prompt (next section).
3. `python -m py_compile /abs/path/{name}.py`; then put the `.py` path in `done_tool` reasoning to register.

### Writing the HTML prompt (this is where agent quality lives)

Copy `html_prompt_template.html` to `extension/prompt/{name}.html`, set `<meta name="name">` to the agent's name, and fill each block. The prompt is the agent's brain — treat it with the same care as a skill.

**Structure (do not break it):**
- **system**: `profile`, `language-settings`, `project`, `input-rules`, `constraint-rules`, `task-rules`, `context-rules`, `response-protocol`.
- **user**: an `<agent-context>` **container** holding `task` / `constraints` / `step-info` / `memory` / (`todo`) / `workspace` / (`errors`), with `<tool-context>`, `<skill-context>`, `<connector-context>` as **siblings** of `<agent-context>` (NOT nested). The CSS/renderer depends on this container-vs-sibling layout.

**What each block is for** (fill the agent-specific ones; keep the shared ones roughly as the template has them):
- `profile` *(agent-specific)* — who the agent is and its core behavior; explain the WHY, not just rules.
- `language-settings` *(shared)* — working language and "reply in the request's language".
- `project` *(agent-specific)* — the paths this agent may read/write and its permission posture (read-only vs edit). This is a real guardrail — say exactly where it may write.
- `input-rules` *(agent-specific)* — what each context sub-module means and which `inspect_*` tool this agent uses.
- `constraint-rules` *(shared)* — the resource-budget / urgency-tier contract (NORMAL / TIGHT / CRITICAL).
- `task-rules` *(agent-specific)* — the agent's objective and when to call `done_tool`.
- `context-rules` *(shared)* — how memory is presented, and that it must use only the listed tools/skills/connectors (ignoring any not loaded).
- `response-protocol` *(shared)* — that it acts by **calling tools natively** (not by emitting a JSON plan), and signals completion only via `done_tool`.
- `agent-context` + `tool/skill/connector-context` *(shared frame)* — the live-state and capability slots; only the template variables below go here.

> **Shared blocks & modules.** The built-in default agents in `autogenesis/prompt/default/` factor the shared blocks (`language-settings`, `constraint-rules`, `context-rules`, `response-protocol`, `agent-context`) into `autogenesis/prompt/module/*.html`, referenced with `<module src="../module/NAME.html"></module>` (the server inlines them into the message; `prompt.js` inlines them for browser viewing). **Generated agents keep these blocks inline** — do NOT use `<module src>` in an `extension/prompt/` file: module `src` is resolved relative to the prompt file, so `../module/...` only exists under `autogenesis/prompt/default/` and would fail to load from `extension/prompt/`.

**Template-variable contract** — use only the variables the base context builder provides, spelled exactly:
`{{ task }}`, `{{ constraint_text }}`, `{{ step_info }}`, `{{ memory_context }}`, `{{ workspace }}`, `{{ errors }}`, `{{ todo }}`, `{{ available_tools }}`, `{{ available_skills }}`, `{{ available_connectors }}`, plus the system-side `{{ extension_root }}`, `{{ workspace_root }}`. Inventing a variable leaves an empty slot; misspelling one silently drops that context.

**Response contract — native tool calls (NOT a JSON plan)**: the base loop turns the agent's capabilities into native tools and reads the model's `tool_calls` each step; it does NOT parse a JSON `plan`/`output-schema` from the text. So `response-protocol` must tell the agent to **act by calling tools** and to finish only by calling `done_tool`. (Older prompts used a `plan`/`output-schema` JSON contract — that is obsolete; do not reintroduce it.)

**Writing principles (borrowed from good skill authoring):**
- Prefer the imperative. Define concrete rules, not vague directives.
- **Explain the WHY.** Modern models have good theory of mind — when you explain why a rule matters, they generalize instead of following it brittly. All-caps ALWAYS/NEVER and rigid structures are a yellow flag: reframe as reasoning.
- Keep it lean — every line should earn its place. Remove instructions that don't change behavior.
- Make the `profile` and `task-rules` say clearly what the agent is for and how it should approach work.
- Draft it, then reread with fresh eyes and cut/clarify.

---

## Evaluating an agent

Call `inspect_agent_tool` on the target for its registry facts (registered / instantiated / version / file paths). Score across five dimensions (0–20 each):

1. **Interface Compliance** — `@AGENT.register_module`, inherits `Agent`, has `name`/`description`/`metadata`/`enable_evolving`; **cleanly inherits the base loop**. Tool-calling agents must not override `__call__`; procedural agents subclass `ProceduralAgent` and implement `run_procedure`.
2. **Code Quality** — clean, valid, no dead code; lifecycle hooks come from the inherited loop, not re-implemented.
3. **Prompt Quality** — HTML present (tool-calling) with the required sections, the container-vs-sibling `agent-context` layout, correct template variables, and a `response-protocol` that drives **native tool calls** (no obsolete JSON `plan`/`output-schema`). Auto-pass for procedural agents (no prompt).
4. **Integration** — `inspect_agent_tool` shows Registered + Instantiated.
5. **Task Execution** — a valid execution path: a tool-calling agent with a valid `prompt_name` inheriting the loop, or a `ProceduralAgent` implementing `run_procedure`.

For an empirical check, MetaAgent can dispatch the agent on a sample task and inspect the result.

---

## Improving an agent

Most agent improvement is **prompt improvement**. The target is named in the task. Call `inspect_agent_tool` FIRST for its file paths and `enable_evolving` — if `enable_evolving=False`, the agent is frozen; do NOT edit it, report and stop. (The built-in default agents are all frozen; the optimizer edits generated agents under `extension/`, which keep every block inline.)

- Read the Python and HTML before editing. Decide whether the fix is in the **prompt** (behavior, rules, reasoning — most common) or the **class** (a real code bug).
- Make the smallest correct change. Preserve `@AGENT.register_module`, `name`, and the prompt's `agent-context` structure and template variables.
- If you ever edit a `autogenesis/prompt/default/` agent and see a `<module src="../module/NAME.html">` tag, that block is a **shared module** used by many agents — editing the module file changes all of them; to change one agent only, inline the block into that file first.
- Keep the class thin — prefer fixing the prompt over adding loop overrides. If you see an unnecessary override of `_get_agent_context`/`_think_and_act`, that's a candidate to remove.
- Apply the prompt writing principles above: explain the why, cut dead instructions, sharpen the rules the agent kept getting wrong.
- Verify with `py_compile` (and that the HTML still has valid template variables), then re-register by putting the edited file path in `done_tool` reasoning.

---

## Orchestration (for MetaAgent)

1. **Generate** — dispatch `agent_generate_agent` with the intent; it writes the class/prompt/config from the templates and registers.
2. **Evaluate** — dispatch `agent_evaluate_agent` (optionally after a sample run) to score.
3. **Improve** — dispatch `agent_optimize_agent` with the evaluation; it edits (usually the prompt) and re-registers.
4. **Repeat** until the agent is good.

---

## Reference files

- `references/tool_calling_agent_template.py` — thin tool-calling agent class.
- `references/procedural_agent_template.py` — deterministic procedural agent.
- `references/html_prompt_template.html` — HTML prompt skeleton (structure + template-variable contract).
