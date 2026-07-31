from mmengine.config import read_base
with read_base():
    from .base import memory_config, window_size, max_tokens
    from .agents.code_agent import code_agent
    from .tools.bash import bash_tool
    from .tools.read_file import read_file_tool
    from .tools.write_file import write_file_tool
    from .tools.edit_file import edit_file_tool
    from .tools.list_dir import list_dir_tool
    from .tools.git import git_tool
    from .tools.glob_search import glob_search_tool
    from .tools.grep_search import grep_search_tool
    from .tools.deploy import deploy_tool
    from .memory.file_system_memory import file_system_memory

tag = "code_agent"
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
    "code_agent",
]
tool_names = [
    "bash_tool",
    "done_tool",
    "read_file_tool",
    "write_file_tool",
    "edit_file_tool",
    "list_dir_tool",
    "git_tool",
    "glob_search_tool",
    "grep_search_tool",
    "deploy_tool",
    "inspect_tool",
    "todo_tool",
]
skill_names = []
connector_names = [
    "biorxiv_connector",
    "chembl_connector",
    "clinical_trials_connector",
    "pubmed_connector",
]

#-----------------TOOL CONFIGS-----------------
bash_tool.update(
    enable_evolving=False,
)
git_tool.update(
    timeout=60,
)

#-----------------MEMORY SYSTEM CONFIG-----------------
file_system_memory.update(
    base_dir="memory/file_system",
    model_name=model_name,
    enable_evolving=False,
)

#-----------------CODE AGENT CONFIG-----------------
code_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)
