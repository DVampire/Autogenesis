monitor_agent = dict(
    type          = "MonitorAgent",
    name          = "monitor_agent",
    description   = (
        "Starts a long-running bash process and monitors it, "
        "reporting progress to the parent agent at regular intervals."
    ),
    poll_interval = 30,    # seconds between progress reports
    max_wait      = 3600,  # kill process after this many seconds
    tail_lines    = 50,    # stdout lines included in each progress snapshot
    enable_evolving  = False,
)
