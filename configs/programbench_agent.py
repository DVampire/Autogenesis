"""Config for examples/run_programbench.py.

Base roster for a pure ProgramBench code-reconstruction run: MetaAgent +
code/general/reviewer actor agents, plus every optimizer/generator/evaluator
agent, `evolution_tool`, and `self_evolving_skill` are imported and configured
here too (so their settings exist) but are NOT in the default
`agent_names`/`tool_names`/`skill_names` lists below — the running script's
`extend_roster_for_evolve()` appends them at runtime when `--evolve` is set
(the default). No browser/connector/environment wiring — irrelevant to a
code-reconstruction task.

`bash_tool` is the ONLY tool in this repo that actually checks
`get_current_sandbox()` (autogenesis/tool/default/bash.py) and routes into a
bound real Docker sandbox — confirmed by grepping the whole codebase for
`get_current_sandbox` usage. `read_file_tool`/`write_file_tool`/`edit_file_tool`/
`list_dir_tool`/`git_tool` only ever check `check_session_path` (a host
filesystem path-boundary check, autogenesis/sandbox/project.py) and
`monitor_agent` spawns its own `asyncio.create_subprocess_shell` directly —
neither path has any sandbox awareness at all, so all five would silently
operate on the (nearly empty, once a Docker sandbox is bound) *host* workspace
directory instead of the container's `/workspace`, giving the agent an
inconsistent view of its own environment and letting file-tool writes go
missing from `extract_submission()`'s tar of the container. All five are
therefore deliberately absent below — `bash_tool` alone covers every file/git
operation the agent needs (matches the official mini-swe-agent ProgramBench
baseline, which likewise only gives the agent a single bash tool).
"""
from mmengine.config import read_base
with read_base():
    from .base import memory_config, window_size, max_tokens
    from .agents.meta_agent import meta_agent
    from .agents.code_agent import code_agent
    from .agents.general_agent import general_agent
    from .agents.reviewer_agent import reviewer_agent
    from .agents.tool_optimize_agent import tool_optimize_agent
    from .agents.tool_evaluate_agent import tool_evaluate_agent
    from .agents.tool_generate_agent import tool_generate_agent
    from .agents.agent_generate_agent import agent_generate_agent
    from .agents.agent_optimize_agent import agent_optimize_agent
    from .agents.agent_evaluate_agent import agent_evaluate_agent
    from .agents.skill_generate_agent import skill_generate_agent
    from .agents.skill_optimize_agent import skill_optimize_agent
    from .agents.skill_evaluate_agent import skill_evaluate_agent
    from .agents.environment_generate_agent import environment_generate_agent
    from .agents.environment_optimize_agent import environment_optimize_agent
    from .agents.environment_evaluate_agent import environment_evaluate_agent
    from .agents.connector_generate_agent import connector_generate_agent
    from .agents.connector_optimize_agent import connector_optimize_agent
    from .agents.connector_evaluate_agent import connector_evaluate_agent
    from .tools.bash import bash_tool
    from .tools.evolution import evolution_tool
    from .tools.escalate import escalate_tool
    from .memory.file_system_memory import file_system_memory

tag = "programbench_agent"
# Pre-binding default only: bind_session_roots() repoints this at the
# session sandbox as soon as real work starts. `tag` stays as a label,
# not a directory level, so it cannot collide with an owner name.
project_root = "output/.runtime/unbound"
log_path = "agent.log"

model_name = "google/gemini-3.1-pro-preview"

memory_names = [
    "file_system_memory",
]

# Base roster — extended at runtime by examples/run_programbench.py's
# extend_roster_for_evolve() when --evolve is set (default: on).
# monitor_agent is deliberately excluded: it spawns its own bash subprocess
# directly (asyncio.create_subprocess_shell), bypassing the Docker sandbox
# bash_tool routes through — see the module docstring above.
agent_names = [
    "meta_agent",
    "code_agent",
    "general_agent",
    "reviewer_agent",
]
# read_file_tool/write_file_tool/edit_file_tool/list_dir_tool/git_tool are
# deliberately excluded: none of them check get_current_sandbox(), so they'd
# silently operate on the host workspace instead of the container — see the
# module docstring above. bash_tool alone covers every file/git operation.
tool_names = [
    "bash_tool",
    "done_tool",
    "escalate_tool",
    "reply_tool",
]
skill_names = [
    "code_review_skill",
    "security_review_skill",
    "simplify_skill",
    "review_skill",
    "verify_skill",
    "run_skill",
    "init_skill",
    "planning_and_task_breakdown_skill",
    "spec_driven_development_skill",
    "context_engineering_skill",
    "doubt_driven_development_skill",
    "test_driven_development_skill",
    "debugging_and_error_recovery_skill",
    "source_driven_development_skill",
    "api_and_interface_design_skill",
    "incremental_implementation_skill",
    "documentation_and_adrs_skill",
    "git_workflow_and_versioning_skill",
    "performance_optimization_skill",
    "observability_and_instrumentation_skill",
]
connector_names = []
env_names = []

#-----------------TOOL CONFIGS-----------------
# permission_mode is already "danger_full_access" at the tool's own base default
# (configs/tools/bash.py) — no need to restate it here, matching meta_agent.py/hle.py.
bash_tool.update(enable_evolving=False)

#-----------------MEMORY SYSTEM CONFIG-----------------
file_system_memory.update(
    base_dir="memory/file_system",
    model_name=model_name,
    enable_evolving=False,
)

#-----------------ACTOR AGENT CONFIGS-----------------
code_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

general_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

reviewer_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

#-----------------OPTIMIZER/GENERATOR/EVALUATOR AGENT CONFIGS (self-evolution roster)-----------------
tool_optimize_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

tool_generate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

tool_evaluate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

agent_generate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

agent_optimize_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

agent_evaluate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

skill_generate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

skill_optimize_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

skill_evaluate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

environment_generate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

environment_optimize_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

environment_evaluate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

connector_generate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

connector_optimize_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

connector_evaluate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

#-----------------META AGENT CONFIG-----------------
meta_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
    max_step=50,
)
