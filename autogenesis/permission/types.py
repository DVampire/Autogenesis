"""Permission system for Autogenesis.

Standalone module — apply to any entity: tool, agent, skill.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Core enums
# ---------------------------------------------------------------------------

class PermissionMode(str, Enum):
    """Coarse permission level assigned to an entity at config time."""
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


class Operation(str, Enum):
    """The operation type for a permission check."""
    BASH = "bash"
    READ = "read"
    WRITE = "write"


class CommandIntent(str, Enum):
    """Semantic classification of a shell command."""
    READ_ONLY = "read_only"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    NETWORK = "network"
    PROCESS_MANAGEMENT = "process_management"
    PACKAGE_MANAGEMENT = "package_management"
    SYSTEM_ADMIN = "system_admin"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Permission request (input to check())
# ---------------------------------------------------------------------------

class PermissionRequest(BaseModel):
    """Unified input for a permission check.

    Usage:
        PermissionRequest(op=Operation.BASH, target="rm -rf /tmp/foo")
        PermissionRequest(op=Operation.READ, target="/path/to/file.py")
        PermissionRequest(op=Operation.WRITE, target="/path/to/file.py", content="...")
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    op: Operation = Field(description="Operation type: bash / read / write")
    target: str = Field(description="Command string (bash) or file path (read/write)")
    content: str = Field(default="", description="File content — only used for write ops")


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of a permission / validation check."""
    allowed: bool
    warning: Optional[str] = None
    reason: Optional[str] = None      # set when allowed=False

    @staticmethod
    def allow(warning: Optional[str] = None) -> "ValidationResult":
        return ValidationResult(allowed=True, warning=warning)

    @staticmethod
    def block(reason: str) -> "ValidationResult":
        return ValidationResult(allowed=False, reason=reason)

    @staticmethod
    def warn(message: str) -> "ValidationResult":
        return ValidationResult(allowed=True, warning=message)


# ---------------------------------------------------------------------------
# Bash validation pipeline (ported from claw-code bash_validation.rs)
# ---------------------------------------------------------------------------

_READ_ONLY_COMMANDS = frozenset({
    "cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg",
    "find", "ls", "ll", "la", "lstat", "stat", "file", "wc", "diff", "diff3",
    "sdiff", "cmp", "md5sum", "sha1sum", "sha256sum", "sha512sum", "cksum",
    "xxd", "hexdump", "od", "strings", "du", "df", "pwd", "date", "uptime",
    "uname", "hostname", "whoami", "id", "groups", "env", "printenv", "set",
    "echo", "printf", "true", "false", "test", "[", "[[",
    "git", "hg", "svn",
    "man", "info", "help", "which", "whereis", "type", "hash",
    "ps", "top", "htop", "pgrep", "jobs",
    "ping", "traceroute", "netstat", "ss", "ifconfig", "ip", "nslookup", "dig",
    "curl", "wget",
    "python", "python3", "node", "ruby", "perl", "lua",
    "cargo", "go", "make", "cmake",
    "jq", "yq", "xmllint",
    "sort", "uniq", "cut", "tr", "awk", "sed", "tee",
})

_DESTRUCTIVE_COMMANDS = frozenset({
    "rm", "rmdir", "mv", "dd", "mkfs", "format",
    "shred", "wipe", "truncate", "fdisk", "parted",
    "kill", "killall", "pkill",
})

_SYSTEM_ADMIN_COMMANDS = frozenset({
    "sudo", "su", "doas",
    "chmod", "chown", "chgrp",
    "mount", "umount",
    "iptables", "nftables", "ufw",
    "systemctl", "service", "init",
    "useradd", "userdel", "usermod", "passwd",
    "crontab",
})

_PACKAGE_MANAGERS = frozenset({
    "apt", "apt-get", "dpkg", "yum", "dnf", "rpm", "zypper",
    "brew", "port", "pkg",
    "pip", "pip3", "conda", "poetry", "pipenv",
    "npm", "yarn", "pnpm", "bun",
    "gem", "cargo", "go",
})

_GIT_WRITE_SUBCOMMANDS = frozenset({
    "commit", "push", "pull", "fetch", "merge", "rebase", "reset",
    "checkout", "switch", "restore", "stash", "tag", "branch",
    "add", "rm", "mv", "clean", "apply", "cherry-pick", "revert",
    "bisect", "worktree", "submodule", "remote",
    "am", "format-patch", "send-email",
    "gc", "prune", "pack-refs", "reflog", "config",
})

_SED_INPLACE_RE = re.compile(r"\bsed\b.*-[a-zA-Z]*i")
_REDIRECT_WRITE_RE = re.compile(r"(?<![<>])>(?!>)")
_SHELL_COMPOSITION_RE = re.compile(r"(?:&&|\|\||[;|`]|\$\(|\n)")


def _classify_intent(command: str) -> CommandIntent:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return CommandIntent.UNKNOWN
    if not tokens:
        return CommandIntent.UNKNOWN

    prog = os.path.basename(tokens[0])

    if prog in _DESTRUCTIVE_COMMANDS:
        return CommandIntent.DESTRUCTIVE
    if prog in _SYSTEM_ADMIN_COMMANDS:
        return CommandIntent.SYSTEM_ADMIN
    if prog in _PACKAGE_MANAGERS:
        return CommandIntent.PACKAGE_MANAGEMENT
    if prog == "git" and len(tokens) > 1:
        return CommandIntent.WRITE if tokens[1] in _GIT_WRITE_SUBCOMMANDS else CommandIntent.READ_ONLY
    # General-purpose interpreters, network clients and build tools are not
    # read-only merely because their executable name looks familiar. They can
    # write arbitrary files or run arbitrary child commands.
    if prog in {"python", "python3", "node", "ruby", "perl", "lua", "curl", "wget",
                "cargo", "go", "make", "cmake", "tee"}:
        return CommandIntent.UNKNOWN
    if prog in _READ_ONLY_COMMANDS:
        return CommandIntent.READ_ONLY
    return CommandIntent.UNKNOWN


def _validate_mode(command: str, mode: PermissionMode) -> Optional[ValidationResult]:
    if mode == PermissionMode.DANGER_FULL_ACCESS:
        return None

    intent = _classify_intent(command)

    if mode == PermissionMode.READ_ONLY:
        if intent in (CommandIntent.DESTRUCTIVE, CommandIntent.WRITE,
                      CommandIntent.SYSTEM_ADMIN, CommandIntent.PACKAGE_MANAGEMENT,
                      CommandIntent.UNKNOWN):
            return ValidationResult.block(
                f"Command blocked in read_only mode (classified as {intent.value}): {command!r}"
            )
        if _REDIRECT_WRITE_RE.search(command):
            return ValidationResult.block(
                f"Output redirect blocked in read_only mode: {command!r}"
            )
        if _SHELL_COMPOSITION_RE.search(command):
            return ValidationResult.block(
                f"Composed shell command blocked in read_only mode: {command!r}"
            )

    if mode == PermissionMode.WORKSPACE_WRITE:
        if intent == CommandIntent.SYSTEM_ADMIN:
            return ValidationResult.block(
                f"System-admin command blocked in workspace_write mode: {command!r}"
            )

    return None


def _validate_sed(command: str, mode: PermissionMode) -> Optional[ValidationResult]:
    if _SED_INPLACE_RE.search(command):
        if mode == PermissionMode.READ_ONLY:
            return ValidationResult.block(
                f"In-place sed blocked in read_only mode: {command!r}"
            )
        return ValidationResult.warn("In-place sed modifies files; ensure this is intentional.")
    return None


def _check_destructive(command: str) -> Optional[ValidationResult]:
    warnings = []
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None

    prog = os.path.basename(tokens[0]) if tokens else ""

    if prog == "rm":
        flags = " ".join(t for t in tokens if t.startswith("-"))
        if any(t in ("/*", "/") for t in tokens[1:]):
            return ValidationResult.block("Refusing to run rm on root path.")
        if "-r" in flags or "--recursive" in flags:
            if "-f" in flags or "--force" in flags:
                warnings.append("'rm -rf' is irreversible — double-check the target path.")
            else:
                warnings.append("Recursive rm detected.")

    if prog in ("dd", "mkfs"):
        warnings.append(f"'{prog}' can destroy data — verify arguments carefully.")

    if prog == "kill" and "-9" in tokens:
        warnings.append("SIGKILL (-9) cannot be caught — the process will not clean up.")

    return ValidationResult.warn(" ".join(warnings)) if warnings else None


def validate_command(command: str, mode: PermissionMode, workspace: str = "") -> ValidationResult:
    """Full bash validation pipeline.

    All checks run; first block wins, all warnings are collected and joined.
    """
    warnings = []
    for check in (
        lambda: _validate_mode(command, mode),
        lambda: _validate_sed(command, mode),
        lambda: _check_destructive(command),
    ):
        result = check()
        if result is None:
            continue
        if not result.allowed:
            return result
        if result.warning:
            warnings.append(result.warning)

    return ValidationResult.warn("; ".join(warnings)) if warnings else ValidationResult.allow()


# ---------------------------------------------------------------------------
# File permission helpers
# ---------------------------------------------------------------------------

MAX_READ_SIZE = 10 * 1024 * 1024
MAX_WRITE_SIZE = 10 * 1024 * 1024
BINARY_PROBE_BYTES = 8192


def is_binary_file(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(BINARY_PROBE_BYTES)
        return b"\x00" in chunk
    except OSError:
        return False


def check_file_read(path: str, mode: PermissionMode, workspace: str = "") -> ValidationResult:
    try:
        size = os.path.getsize(path)
    except OSError:
        return ValidationResult.allow()

    if size > MAX_READ_SIZE:
        return ValidationResult.block(
            f"File too large to read: {size / 1024 / 1024:.1f} MB (limit 10 MB)."
        )
    if is_binary_file(path):
        return ValidationResult.block("Binary file detected — use a dedicated binary tool instead.")
    return ValidationResult.allow()


def check_file_write(path: str, content: str, mode: PermissionMode, workspace: str = "") -> ValidationResult:
    if mode == PermissionMode.READ_ONLY:
        return ValidationResult.block("File writes are not allowed in read_only mode.")

    encoded = content.encode("utf-8", errors="replace")
    if len(encoded) > MAX_WRITE_SIZE:
        return ValidationResult.block(
            f"Content too large to write: {len(encoded) / 1024 / 1024:.1f} MB (limit 10 MB)."
        )

    if workspace and mode == PermissionMode.WORKSPACE_WRITE:
        try:
            resolved = os.path.realpath(path)
            # The workspace holds user deliverables; the extension root is the
            # staging tree a generator agent writes evolved capabilities into. It
            # deliberately sits beside the workspace rather than inside it, so it
            # has to be named here or creating any extension component is blocked.
            roots = [os.path.realpath(workspace)]
            try:
                from autogenesis.config import config as _config

                extension_root = getattr(_config, "extension_root", "")
                if extension_root:
                    roots.append(os.path.realpath(str(extension_root)))
            except Exception:  # noqa: BLE001 - config is optional here
                pass

            def _inside(target: str, root: str) -> bool:
                try:
                    return os.path.commonpath((target, root)) == root
                except ValueError:
                    return False

            if not any(_inside(resolved, root) for root in roots):
                return ValidationResult.block(
                    f"Path {path!r} is outside the writable roots {roots!r}."
                )
        except Exception:
            pass

    return ValidationResult.allow()


# ---------------------------------------------------------------------------
# Composable policy conditions (policy_engine.rs pattern)
# ---------------------------------------------------------------------------

class PolicyCondition:
    """Abstract base for composable policy conditions."""
    def evaluate(self, entity_name: str, target: str) -> bool:
        raise NotImplementedError


class GlobCondition(PolicyCondition):
    """True when entity_name and target both match fnmatch glob patterns."""
    def __init__(self, entity_pattern: str, target_pattern: str):
        self.entity_pattern = entity_pattern
        self.target_pattern = target_pattern

    def evaluate(self, entity_name: str, target: str) -> bool:
        return (
            fnmatch.fnmatch(entity_name, self.entity_pattern)
            and fnmatch.fnmatch(target.strip(), self.target_pattern)
        )


class AndCondition(PolicyCondition):
    """True only when ALL sub-conditions are true (short-circuits on first False)."""
    def __init__(self, *conditions: PolicyCondition):
        self.conditions = list(conditions)

    def evaluate(self, entity_name: str, target: str) -> bool:
        return all(c.evaluate(entity_name, target) for c in self.conditions)


class OrCondition(PolicyCondition):
    """True when ANY sub-condition is true (short-circuits on first True)."""
    def __init__(self, *conditions: PolicyCondition):
        self.conditions = list(conditions)

    def evaluate(self, entity_name: str, target: str) -> bool:
        return any(c.evaluate(entity_name, target) for c in self.conditions)


class NotCondition(PolicyCondition):
    """Negates a sub-condition."""
    def __init__(self, condition: PolicyCondition):
        self.condition = condition

    def evaluate(self, entity_name: str, target: str) -> bool:
        return not self.condition.evaluate(entity_name, target)


# ---------------------------------------------------------------------------
# Rule-based policy
# ---------------------------------------------------------------------------

class RuleAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class PermissionRule:
    """Single allow/deny rule — fnmatch glob on entity_name and target."""
    action: RuleAction
    entity_pattern: str
    target_pattern: str

    def matches(self, entity_name: str, target: str) -> bool:
        return (
            fnmatch.fnmatch(entity_name, self.entity_pattern)
            and fnmatch.fnmatch(target.strip(), self.target_pattern)
        )


@dataclass
class PermissionPolicy:
    """Ordered list of allow/deny rules, evaluated top-to-bottom."""
    rules: List[PermissionRule] = field(default_factory=list)
    default_action: RuleAction = RuleAction.ALLOW

    def authorize(self, entity_name: str, target: str) -> ValidationResult:
        for rule in self.rules:
            if rule.matches(entity_name, target):
                if rule.action == RuleAction.DENY:
                    return ValidationResult.block(
                        f"Denied by policy rule '{rule.entity_pattern}({rule.target_pattern})'."
                    )
                return ValidationResult.allow()
        if self.default_action == RuleAction.DENY:
            return ValidationResult.block("Denied by default policy.")
        return ValidationResult.allow()


# ---------------------------------------------------------------------------
# PermissionEnforcer
# ---------------------------------------------------------------------------

class PermissionEnforcer:
    """Per-entity enforcer — dispatches check() based on operation type."""

    def __init__(
        self,
        entity_name: str,
        mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
        workspace: str = "",
        policy: Optional[PermissionPolicy] = None,
    ):
        self.entity_name = entity_name
        self.mode = mode
        self.workspace = workspace
        self.policy = policy or PermissionPolicy()

    def check(self, input: PermissionRequest, **kwargs) -> ValidationResult:
        """Unified check — dispatches on input.op."""
        workspace = str(kwargs.get("workspace") or self.workspace)
        if input.op == Operation.BASH:
            result = validate_command(input.target, self.mode, workspace)
            if not result.allowed:
                return result
            policy_result = self.policy.authorize(self.entity_name, input.target)
            if not policy_result.allowed:
                return policy_result
            return result  # may carry a warning

        if input.op == Operation.READ:
            return check_file_read(input.target, self.mode, workspace)

        if input.op == Operation.WRITE:
            result = check_file_write(input.target, input.content, self.mode, workspace)
            if not result.allowed:
                return result
            policy_result = self.policy.authorize(self.entity_name, input.target)
            if not policy_result.allowed:
                return policy_result
            return result

        return ValidationResult.allow()


__all__ = [
    "PermissionMode",
    "Operation",
    "CommandIntent",
    "PermissionRequest",
    "ValidationResult",
    "PolicyCondition", "GlobCondition", "AndCondition", "OrCondition", "NotCondition",
    "PermissionRule",
    "RuleAction",
    "PermissionPolicy",
    "PermissionEnforcer",
    "validate_command",
    "check_file_read",
    "check_file_write",
    "is_binary_file",
    "MAX_READ_SIZE",
    "MAX_WRITE_SIZE",
]
