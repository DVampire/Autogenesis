"""Config for running MonitorAgent standalone (without MetaAgent).

Usage
-----
# Default demo command (sleep 90, reports twice before finishing)
python examples/run_monitor_agent.py

# Custom command
python examples/run_monitor_agent.py --command "bash my_long_job.sh"

# Override poll interval
python examples/run_monitor_agent.py --cfg-options monitor_agent.poll_interval=10
"""

from mmengine.config import read_base

with read_base():
    from .base import max_tokens, window_size
    from .agents.monitor_agent import monitor_agent

tag         = "monitor_agent"
# Pre-binding default only: bind_session_roots() repoints this at the
# session sandbox as soon as real work starts. `tag` stays as a label,
# not a directory level, so it cannot collide with an owner name.
project_root = "output/.runtime/unbound"
log_path    = "monitor_agent.log"

model_name      = "google/gemini-3.1-pro-preview"

agent_names  = ["monitor_agent"]
tool_names   = []
skill_names  = []
connector_names = []
memory_names = []

monitor_agent.update(
    enable_evolving = False,
)
