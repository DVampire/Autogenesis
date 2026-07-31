from mmengine.config import read_base
with read_base():
    from .base import memory_config, window_size, max_tokens
    from .agents.general_agent import general_agent
    from .tools.mdify import mdify_tool
    from .tools.bash import bash_tool
    from .memory.file_system_memory import file_system_memory

tag = "general_agent"
# Pre-binding default only: bind_session_roots() repoints this at the
# session sandbox as soon as real work starts. `tag` stays as a label,
# not a directory level, so it cannot collide with an owner name.
project_root = "output/.runtime/unbound"
log_path = "agent.log"

version = "0.1.0"
model_name = "google/gemini-3.1-pro-preview"

memory_names = [
    "file_system_memory",
]
agent_names = [
    "general_agent"
]
tool_names = [
    'bash_tool',
    'code_interpreter_tool',
    'done_tool',
    'inspect_tool',
    'todo_tool',
]
skill_names = [
    "hello_world_skill",
]
connector_names = [
    "biorxiv_connector",
    "chembl_connector",
    "clinical_trials_connector",
    "pubmed_connector",
]

#-----------------BASH TOOL CONFIG-----------------
bash_tool.update(
    enable_evolving=False,
)
#-----------------MDIFY TOOL CONFIG-----------------
mdify_tool.update(
    base_dir="tool/mdify",
)

#-----------------MEMORY SYSTEM CONFIG-----------------
file_system_memory.update(
    base_dir="memory/file_system",
    model_name=model_name,
    enable_evolving=False,
)

#-----------------REASON ACT AGENT CONFIG-----------------
general_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)
