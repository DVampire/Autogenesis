meta_agent = dict(
    name = "meta_agent",
    type = "Agent",
    description = "Orchestrator that decomposes tasks, dispatches sub-agents concurrently, reacts to results, and triggers self-evolution (generate/optimize/evaluate + reviewer) when a capability is missing or a sub-agent underperforms.",
    model_name = "google/gemini-3.1-pro-preview",
    prompt_name = "meta_agent",
    memory_name = "file_system_memory",
    max_step = 50,
    max_token = 5000000,
    timeout = 7200,
    enable_evolving = False,
    use_memory = True,
)
