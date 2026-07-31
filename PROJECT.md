
# Autogenesis

A self-evolving multi-agent framework. A MetaAgent orchestrates sub-agents to complete user tasks, while generator/evaluator/optimizer agents continuously create and improve the evolvable ecosystem — tools, agents, skills, connectors (MCP servers), and environments.

## Directory Structure

```
Autogenesis/
├── autogenesis/           # Core framework. Most component modules share one shape:
│   │                       #   default/ (built-ins) + types.py (base class + context) +
│   │                       #   server.py (the *_manager singleton). Only notable extras are listed.
│   ├── agent/              # Agents (built-ins; evolved ones → extension/)
│   │   ├── actor/          #   Task-doing: Meta, Code, General, Browser, Monitor, Reviewer
│   │   ├── generator/      #   Create new components (one *_generate_agent per type)
│   │   ├── evaluator/      #   Score component quality (one *_evaluate_agent per type)
│   │   └── optimizer/      #   Evolve existing component source (one *_optimize_agent per type)
│   ├── tool/               # Tools — default/ (bash, file r/w/edit, git, done, ...), workflow/ (todo), other/
│   ├── prompt/             # Prompt templates (one HTML per agent)
│   ├── skill/              # Skills (multi-step SOP workflows), in category folders scanned for SKILL.md:
│   │   ├── creator/        #   Self-evolution — *_creator_skill (per type), self_evolving_skill
│   │   ├── methodology/    #   Engineering practice: TDD, incremental dev, debugging, API design, git
│   │   ├── orchestrate/    #   Planning & context: task breakdown, spec/doubt-driven dev, context_engineering
│   │   ├── review/         #   Quality gates: code/security review, verify, simplify, perf
│   │   ├── authoring/      #   Deliverables: docx/pdf/pptx/xlsx, report/artifact design, doc_coauthoring
│   │   ├── web/            #   Web/app delivery: frontend, webapp testing, deploy, run, ci/cd, migration
│   │   ├── research/       #   Investigation: deep_research, observability
│   │   ├── science/        #   Bio/chem: protein structure/design, diffdock, evo2, scgpt, literature_review
│   │   └── interactive/ · misc/   #   Human-in-the-loop (idea_refine, interview_me) · scaffolding (init)
│   ├── connector/          # Connectors — external MCP servers as tools (CONNECTOR.md-driven);
│   │                       #   built-in bioinformatics/chemistry servers (pubmed, chembl, ...)
│   ├── environment/        # Execution environments (browser, sandbox, ...)
│   ├── sandbox/            # Isolated execution containers — opensandbox backend (infra, not evolvable)
│   ├── deploy/             # Run a web service in a sandbox + bind a URL (Deployer profiles)
│   ├── docker/ · e2b/      # Alternate sandbox backends (scaffolds)
│   ├── benchmark/          # Benchmarks (in src; not hot-pluggable). aime/gpqa/gsm8k/hle/leetcode/...;
│   │                       #   read datasets/ first, else download from HF (ensure_dataset)
│   ├── extension/          # ExtensionManager — loads/evolves the external extension/ tree
│   ├── memory/             # Memory systems (tiered per-session)
│   ├── hook/               # Hook pipeline (compact, memory, trace, ...)
│   ├── trace/              # Observability — raw event log (TraceManager + UI server)
│   ├── trajectory/         # Trainable projection of a run (SFT/RL records)
│   ├── runtime/            # Agent runtime: mailbox + pump + lifecycle
│   ├── protocol/           # Agent-to-agent conversations over the runtime
│   ├── constraint/         # Run budgets (step/token/wall-time)
│   ├── model/              # LLM client (model_manager)
│   ├── data/               # Dataset loaders (DATASET registry)
│   ├── task/ · session/ · permission/ · version/ · config/ · dynamic/
│   │                       #   Task mgmt · session isolation · perms · versioning · config · dynamic class loading
│   ├── queue/ · response/ · message/ · visual/ · logger/ · utils/   # Primitives & shared infra
│   └── registry.py         # mmengine Registry instances (see Registries below)
├── configs/                # mmengine config files (base.py, meta_agent.py, agents/, tools/, memory/)
├── datasets/               # Vendored benchmark datasets
├── extension/              # Hot-pluggable evolved content, OUTSIDE the package (loaded by ExtensionManager):
│   │                       #   flat active files + .versions/ archive + manifest.json (see Conventions)
├── examples/run_meta_agent.py   # Main entry point — MetaAgent orchestrates everything
└── tests/ · scripts/ · others/ · workspace_root/   # Tests · install · scratch notes · per-run output (git-ignored)
```

## Key Concepts

- **`{{ extension_root }}`**: Absolute path to the repo root. Always use it to construct source file paths; never use relative paths.
- **`{{ workspace_root }}`**: Per-run scratch directory for temporary files. Do not write source code here.
- **Built-ins vs extensions**: Hand-written built-ins live in each module's `default/` folder inside `autogenesis/` (e.g. `autogenesis/tool/default/`). Generated/evolved components live OUTSIDE `autogenesis/`, in the external `extension/` tree, and are loaded at runtime by the **ExtensionManager**. `autogenesis/` stays immutable; `extension/` is mutable evolved content.
- **Hot-plug / ExtensionManager** (`autogenesis/extension/`): On startup, after the component managers load their built-ins, `extension_manager.initialize()` layers the active extension set on top. Authoring writes a flat active file (`extension/<module>/<name>.py`); `extension_manager.add_component(...)` registers it via the owning `*_manager`, archives the version under `extension/.versions/`, and records the active version in `extension/manifest.json`. Multiple versions of a component coexist in `.versions/`; `extension_manager.rollback(module, name, version)` restores any of them. There is **no `__init__.py` to edit** for extensions — loading is by directory scan + dynamic import.
- **Registries**: Components self-register with an mmengine `Registry` (in `autogenesis/registry.py`) via a class decorator, e.g. `@TOOL.register_module()`. Built-ins register at import time; extensions are registered at runtime by the ExtensionManager (which loads the class via `dynamic_manager` and calls `<module>_manager.register`).

### Agent loop & interaction

`autogenesis/runtime/` is *how messages move*; `autogenesis/protocol/` is *the shape of each conversation*.

- **One runtime lifecycle for every agent**: tool-calling agents share `on_start → _advance → _think → _dispatch_round → _run_one → _conclude`; deterministic `ProceduralAgent` implementations use the same runtime entry and hooks but implement `run_procedure`. `MetaAgent` remains a normal tool-calling `Agent` with agents and registered workflows projected as capabilities.
- **Dynamic workflows are executable HTML, not an Agent subtype**: MetaAgent can discover an active workflow or generate an ephemeral one; `WorkflowCompiler` validates its restricted control language and `WorkflowRuntime` executes dynamic map/parallel/branch/loop/verify/reduce programs with budgets, cancellation, and checkpoint caching. Side effects still delegate to existing Agent/Tool/Skill/Connector managers.
- **Runtime verbs** (`runtime_manager`): `spawn`, `send` (fire-and-forget), `ask`/`invoke` (run + await `Response`), `suspend`+`resume` (park on a key), `publish`+`subscribe` (topic fan-out).
- **Protocol channels** (`protocol_manager`) are typed conversations over those verbs: **escalation** (gate — a blocked sub-agent asks its parent and suspends until it replies), **delegation**/**query** (ask), **progress**/**control** (tell — cancel/pause/resume), **pubsub** (fan-out).

### The self-evolution loop

The framework evolves its **own** capabilities (tool, agent+prompt, skill, connector, environment) while serving a user task — kept strictly separate from *user work* (done by actor agents like `code_agent`/`general_agent`). Playbook: `skill/creator/self_evolving_skill`.

- **The cycle**: **decide** (a capability is missing/weak) → **generate** (`*_generate_agent` writes a new component) or **optimize** (`*_optimize_agent` edits an existing one's source and re-registers) → **evaluate** (`*_evaluate_agent` scores whether it helped) → **adopt or roll back**.
- **`enable_evolving` gate**: a frozen component (`enable_evolving=False`, e.g. the evolution agents themselves) must never be optimized — checked first, every time.
- **Persistence** (`extension_manager`): writes the flat active file under `extension/<module>/`, archives every version under `.versions/`, records the active one in `manifest.json`; `rollback(module, name, version)` restores any prior version.

### Memory

Per-session, pluggable (`MEMORY_SYSTEM` registry), itself evolvable. The default `TieredMemory` (JSON via `GeneralMemorySystem`, HTML via `FileSystemMemory`) is a state machine fed by `TraceEvent`s:

- **`emit(event)`** syncs into four views: **todos**, **flow_chart** (call path), **recent_history** (raw log), **final_result**.
- **Two tiers**: `recent_history` (raw, bounded); on overflow the oldest records are summarized by the **`compact` hook** into `working_memory` (bounded summaries). `get()` injects the last N summaries + last N raw records for the prompt.

## Conventions

Follow these rules when adding or generating code so the framework can discover and evolve it.

1. **Generated/evolved components go in the external `extension/` tree — never in `autogenesis/`.** Write the flat active file: `extension/tool/<name>.py`, `extension/agent/<name>.py` (+ `extension/prompt/<name>.html`), `extension/skill/<name>/SKILL.md`, `extension/connector/<name>/CONNECTOR.md`, `extension/environment/<name>.py`. The ExtensionManager registers it and archives the version automatically. **Do NOT edit any `__init__.py`** for extensions. Hand-written built-ins (shipped with the framework) go in the module's `autogenesis/<module>/default/` folder (skills/connectors are grouped in category subfolders instead).

2. **Built-ins are exported from `default/__init__.py`; extensions are not.** A new hand-written built-in must be imported in its module's `default/__init__.py` (import + `__all__`) so it registers at import time. Extension components are discovered by directory scan, so they need no `__init__.py` entry.

3. **Register with the right Registry.** Decorate the class with the matching registry decorator (see the table below). Built-ins register on import; extensions are registered at runtime by the ExtensionManager via the same registries.

4. **Keep the module's `types.py` / `server.py` contract.** Subclass the base class in `types.py` and implement its abstract methods; do not bypass the module's `*_manager` singleton in `server.py`.

5. **Benchmarks read data from `datasets/` first, then download from HuggingFace.** Every benchmark stores its data under `datasets/<name>/`. A benchmark declares an `hf_repo_id` field and, in `initialize()`, calls `ensure_dataset(<name>, self.hf_repo_id)` (in `autogenesis/benchmark/utils.py`) before loading: if `datasets/<name>/` is missing/empty it is snapshot-downloaded from HuggingFace, otherwise the local copy is used. Set the `HF_ENDPOINT` env var to use a mirror. Both `hf_repo_id` and `path` are config-overridable.

### Registries (`autogenesis/registry.py`)

| Registry          | Locations         | Decorator                              |
| ----------------- | ----------------- | -------------------------------------- |
| `TOOL`            | `autogenesis.tool`        | `@TOOL.register_module()`              |
| `AGENT`           | `autogenesis.agent`       | `@AGENT.register_module()`             |
| `PROMPT`          | `autogenesis.prompt`      | `@PROMPT.register_module()`            |
| `DATASET`         | `autogenesis.data`        | `@DATASET.register_module()`           |
| `BENCHMARK`       | `autogenesis.benchmark`   | `@BENCHMARK.register_module()`         |
| `SKILL`           | `autogenesis.skill`       | `@SKILL.register_module()`             |
| `HOOK`            | `autogenesis.hook`        | `@HOOK.register_module()`              |
| `CONSTRAINT`      | `autogenesis.constraint`  | `@CONSTRAINT.register_module()`        |
| `ENVIRONMENT`     | `autogenesis.environment` | `@ENVIRONMENT.register_module()`       |
| `MEMORY_SYSTEM`   | `autogenesis.memory`      | `@MEMORY_SYSTEM.register_module()`     |
| `SANDBOX`         | `autogenesis.sandbox`     | `@SANDBOX.register_module()`           |
| `DEPLOYER`        | `autogenesis.deploy`      | `@DEPLOYER.register_module()`          |
| `E2B`             | `autogenesis.e2b`         | `@E2B.register_module()`               |
| `DOCKER`          | `autogenesis.docker`      | `@DOCKER.register_module()`            |

> **Not registry-based:** `connector` (MCP servers), `protocol`, and `trajectory` are managed by their `*_manager` singletons directly — connectors are discovered by scanning `CONNECTOR.md` directories (like skills scan `SKILL.md`), not by a class decorator.
