from mmengine.config import read_base
with read_base():
    from .base import memory_config, window_size, max_tokens
    from .agents.browser_agent import browser_agent
    from .memory.file_system_memory import file_system_memory

tag = "browser_agent"
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
    "browser_agent",
]
# Pure environment agent — no tools; the task ends via the built-in `finish` action.
tool_names = []
skill_names = []
connector_names = []
env_names = [
    "browser_environment",
]

#-----------------BROWSER ENVIRONMENT CONFIG-----------------
# base_dir is joined onto log_root by config.process_environments
# → default/environment/browser; screenshots go to screenshots/<session_id>/
browser_environment = dict(
    base_dir="environment/browser",
    headless=True,
    viewport=dict(width=1024, height=768),
    use_sandbox=False,
    use_som=True,
    state_detail="elements",  # "elements" or "html"
    max_state_elements=0,  # 0 = no truncation (show all interactive elements)
    command_timeout=30.0,
)

#-----------------MEMORY SYSTEM CONFIG-----------------
file_system_memory.update(
    base_dir="memory/file_system",
    model_name=model_name,
    enable_evolving=False,
)

#-----------------BROWSER AGENT CONFIG-----------------
browser_agent.update(
    model_name=model_name,
    memory_name=memory_names[0],
    enable_evolving=False,
    use_memory=True,
)
