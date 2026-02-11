# These are explicitly blocked commands even if writing is allowed
DEFAULT_BLOCKED_COMMANDS: tuple[str] = (
    "cluster-info",  # This would be too much info to return to the LLM
    "get-token",
    "logout",
    "config",
    "completion",
    "plugin",
)

DEFAULT_ALLOWED_COMMANDS: tuple[str] = (
    "status",
    "projects",
    "explain",
    "get",
    "describe",
    "logs",
    "wait",
    "events",
    "version",
    "whoami",
    "api-versions",
    "api-resources",
    "adm node-logs",
    "policy scc-review",
    "policy scc-subject-review",
    "policy who-can",
    "adm top",
    "adm verify-image-signature",  # Not sure how useful it is
    "image info",
    "auth can-i",
    "auth whoami",
    "adm policy scc-review",
    "adm policy scc-subject-review",
    "adm policy who-can",
    "adm wait-for-node-reboot",
    "adm wait-for-stable-cluster",
)
