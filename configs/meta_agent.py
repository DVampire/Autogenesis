from mmengine.config import read_base
with read_base():
    from .base import memory_config, window_size, max_tokens
    from .agents.meta_agent import meta_agent
    from .agents.code_agent import code_agent
    from .agents.general_agent import general_agent
    from .agents.reviewer_agent import reviewer_agent
    from .agents.monitor_agent import monitor_agent
    from .agents.browser_agent import browser_agent
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
    from .agents.memory_generate_agent import memory_generate_agent
    from .agents.memory_optimize_agent import memory_optimize_agent
    from .agents.memory_evaluate_agent import memory_evaluate_agent
    from .agents.connector_generate_agent import connector_generate_agent
    from .agents.connector_optimize_agent import connector_optimize_agent
    from .agents.connector_evaluate_agent import connector_evaluate_agent
    from .tools.bash import bash_tool
    from .tools.read_file import read_file_tool
    from .tools.write_file import write_file_tool
    from .tools.edit_file import edit_file_tool
    from .tools.list_dir import list_dir_tool
    from .tools.git import git_tool
    from .tools.deploy import deploy_tool
    from .tools.evolution import evolution_tool
    from .tools.escalate import escalate_tool
    from .memory.file_system_memory import file_system_memory

tag = "meta_agent"
# Pre-binding default only: bind_session_roots() repoints this at the
# session sandbox as soon as real work starts. `tag` stays as a label,
# not a directory level, so it cannot collide with an owner name.
project_root = "output/.runtime/unbound"
log_path = "agent.log"

model_name = "google/gemini-3.1-pro-preview"

memory_names = [
    "file_system_memory",
]
agent_names = [
    "meta_agent",
    "code_agent",
    "general_agent",
    "reviewer_agent",
    "monitor_agent",
    # browser agent — drives a real browser to VERIFY web/UI deliverables hands-on
    # (render, click, check images/console) via the browser_environment.
    "browser_agent",
    "tool_optimize_agent",
    "tool_evaluate_agent",
    "tool_generate_agent",
    "agent_generate_agent",
    "agent_optimize_agent",
    "agent_evaluate_agent",
    "skill_generate_agent",
    "skill_optimize_agent",
    "skill_evaluate_agent",
    "environment_generate_agent",
    "environment_optimize_agent",
    "environment_evaluate_agent",
    "memory_generate_agent",
    "memory_optimize_agent",
    "memory_evaluate_agent",
    "connector_generate_agent",
    "connector_optimize_agent",
    "connector_evaluate_agent",
]
tool_names = [
    "bash_tool",
    "done_tool",
    "read_file_tool",
    "write_file_tool",
    "edit_file_tool",
    "list_dir_tool",
    "git_tool",
    "deploy_tool",
    "evolution_tool",
    "escalate_tool",
    "reply_tool",
    # web retrieval — search the web, fetch a page, and download REAL images to bundle
    "web_searcher_tool",
    "web_fetcher_tool",
    "media_search_tool",
]
skill_names = [
    # worker skills — the skill pool for this session's sub-agents (code/general/triads).
    "code_review_skill",
    "security_review_skill",
    "deep_research_skill",
    "simplify_skill",
    "review_skill",
    "verify_skill",
    "run_skill",
    "init_skill",
    "report_design_skill",
    "artifact_design_skill",
    "theme_factory_skill",
    "doc_coauthoring_skill",
    # document / data I/O skills — deliver real Office & PDF artifacts
    "docx_skill",
    "xlsx_skill",
    "pdf_skill",
    "pptx_skill",
    # browser automation — test/verify local web apps, capture screenshots
    "webapp_testing_skill",
    # deployment — run a web service in a sandbox and bind it to a URL (drives deploy_tool)
    "deploy_skill",
    # per-type creator skills (orchestrator role) — drive each triad's create->eval->improve loop
    "agent_creator_skill",
    "tool_creator_skill",
    "environment_creator_skill",
    "memory_creator_skill",
    # orchestrator skill: how to drive the skill create->evaluate->improve loop
    "skill_creator_skill",
    # orchestrator skill: how to drive the connector create->evaluate->improve loop
    "connector_creator_skill",
    # global self-evolution playbook: WHEN to evolve + the loop + enable_evolving gate (ties the triads together)
    "self_evolving_skill",
    # engineering-workflow skills (adapted from agent-skills) — orchestrator-side planning/decomposition
    "planning_and_task_breakdown_skill",
    "spec_driven_development_skill",
    "context_engineering_skill",
    "doubt_driven_development_skill",
    # interactive (define/discovery) skills — for task-intake / user turns, not autonomous batch
    "interview_me_skill",
    "idea_refine_skill",
    # build methodology (worker) — how to implement/test/debug/document correctly
    "test_driven_development_skill",
    "debugging_and_error_recovery_skill",
    "source_driven_development_skill",
    "api_and_interface_design_skill",
    "incremental_implementation_skill",
    "documentation_and_adrs_skill",
    "git_workflow_and_versioning_skill",
    # code quality / web / ops (worker)
    "performance_optimization_skill",
    "ci_cd_and_automation_skill",
    "shipping_and_launch_skill",
    "frontend_ui_engineering_skill",
    "deprecation_and_migration_skill",
    "observability_and_instrumentation_skill",
    # science / domain skills (autogenesis/skill/science) — biomodels & bioinformatics workers.
    # GPU-backed structure/sequence models and CPU analysis/design skills; available to
    # sub-agents for drug-discovery, protein, genomics, and single-cell tasks.
    "alphafold2_skill",
    "openfold3_skill",
    "esmfold2_skill",
    "boltz_skill",
    "chai1_skill",
    "diffdock_skill",
    "esm2_skill",
    "evo2_skill",
    "borzoi_skill",
    "scgpt_skill",
    "scvi_tools_skill",
    "proteinmpnn_skill",
    "solublempnn_skill",
    "ligandmpnn_skill",
    "literature_review_skill",
    "indication_dossier_skill",
    "drawio_skill",
]
connector_names = [
    "biomart_connector",
    "cbioportal_connector",
    "cellguide_connector",
    "chemistry_connector",
    "clinical_genomics_connector",
    "drug_regulatory_connector",
    "expression_connector",
    "genes_ontologies_connector",
    "genomes_connector",
    "human_genetics_connector",
    "molecule_toolkit_connector",
    "literature_graph_connector",
    "omics_archives_connector",
    "protein_annotation_connector",
    "regulation_connector",
    "research_resources_connector",
    "rna_connector",
    "structures_interactions_connector",
    "variants_connector",
    "zinc_connector",
    "ketcher_chemistry_connector",
]

#-----------------ENVIRONMENT CONFIGS-----------------
# browser_agent verifies web/UI deliverables in a real browser. Under Model X the
# agent runs in the base container; the browser runs as a separate peer container
# (opensandbox/chrome) spawned via the Docker socket and driven over CDP — so the
# base image needs no chromium of its own. use_sandbox=True selects that peer.
env_names = [
    "browser_environment",
]
browser_environment = dict(
    base_dir="environment/browser",
    headless=True,          # ignored when vnc=True (chrome-vnc forces headful)
    viewport=dict(width=1280, height=900),
    use_sandbox=True,
    vnc=True,               # use the chrome-vnc sandbox (headful Chrome + live noVNC view)
    use_som=True,
    state_detail="elements",
    max_state_elements=0,
    command_timeout=30.0,
)

#-----------------TOOL CONFIGS-----------------
bash_tool.update(enable_evolving=False)
git_tool.update(timeout=60)

#-----------------MEMORY SYSTEM CONFIG-----------------
file_system_memory.update(
    base_dir="memory/file_system",
    model_name=model_name,
    # Evolvable: a long run can expose a retention defect in the memory system
    # itself, and the fix belongs to the memory resource rather than the agent.
    enable_evolving=True,
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

monitor_agent.update(
    enable_evolving=False,
)

browser_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    env_name="browser_environment",
    enable_evolving=False,
    use_memory=True,
)

#-----------------OPTIMIZER AGENT CONFIGS-----------------
tool_optimize_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

#-----------------GENERATOR AGENT CONFIGS-----------------
tool_generate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

#-----------------EVALUATOR AGENT CONFIGS-----------------
tool_evaluate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

#-----------------FULL TRIAD CONFIGS (agent/skill/environment/connector)-----------------
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


#-----------------MEMORY TRIAD CONFIGS-----------------
memory_generate_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

memory_optimize_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)

memory_evaluate_agent.update(
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
    max_step = 50,
)
