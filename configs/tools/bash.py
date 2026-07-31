bash_tool = dict(
    enable_evolving = False,
    # Direct CLI/example runs are explicitly trusted host workflows. Gateway
    # sessions still refuse host execution and require a bound sandbox.
    permission_mode = "danger_full_access",
)
