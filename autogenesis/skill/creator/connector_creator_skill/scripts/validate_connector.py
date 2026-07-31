#!/usr/bin/env python3
"""Quick structural validation for a connector directory (CONNECTOR.md)."""

import os
import re
import sys
from pathlib import Path

import yaml

ALLOWED_PROPERTIES = {
    'name', 'description', 'version', 'type', 'license', 'category',
    'requirements', 'metadata', 'enable_evolving', 'permission_mode',
    'featured', 'connection', 'actions', 'action_schemas',
}


def validate_connector(connector_path):
    connector_path = Path(connector_path)

    md = connector_path / 'CONNECTOR.md'
    if not md.exists():
        return False, "CONNECTOR.md not found"

    content = md.read_text()
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    try:
        fm = yaml.safe_load(match.group(1))
        if not isinstance(fm, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    unexpected = set(fm.keys()) - ALLOWED_PROPERTIES
    if unexpected:
        return False, (
            f"Unexpected key(s) in CONNECTOR.md frontmatter: {', '.join(sorted(unexpected))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # Required fields
    for req in ('name', 'description', 'connection', 'actions'):
        if req not in fm:
            return False, f"Missing '{req}' in frontmatter"

    name = str(fm.get('name', '')).strip()
    if not re.match(r'^[a-z0-9_]+$', name):
        return False, f"Name '{name}' should be snake_case (lowercase letters, digits, underscores)"
    if not name.endswith('_connector'):
        return False, (
            f"Name '{name}' must follow the '<directory>_connector' convention "
            f"(e.g. directory 'pubmed' -> name 'pubmed_connector')"
        )

    # connection must specify a transport and an endpoint (url or command)
    conn = fm.get('connection')
    if not isinstance(conn, dict):
        return False, "'connection' must be a mapping (transport + url/command)"
    if not conn.get('transport'):
        return False, "'connection.transport' is required (streamable_http | sse | stdio)"
    if not (conn.get('url') or conn.get('command')):
        return False, "'connection' must have a 'url' (http/sse) or a 'command' (stdio)"

    # stdio connections must be portable — no machine-specific absolute paths.
    if conn.get('transport') == 'stdio':
        command = str(conn.get('command', ''))
        if os.path.isabs(command):
            return False, (
                f"stdio 'connection.command' should be portable — use 'python' "
                f"(resolved to sys.executable at load time), not the absolute path '{command}'"
            )
        for a in (conn.get('args') or []):
            a = str(a)
            if a.endswith('.py') and os.path.isabs(a):
                return False, (
                    f"stdio 'connection.args' should use a RELATIVE script path "
                    f"(e.g. 'server.py', resolved against the connector dir at load time), "
                    f"not the absolute path '{a}'"
                )

    # actions must be a non-empty list of names
    actions = fm.get('actions')
    if not isinstance(actions, list) or not actions:
        return False, "'actions' must be a non-empty list of action names"

    return True, f"Connector is valid! ({len(actions)} action(s))"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_connector.py <connector_directory>")
        sys.exit(1)
    valid, message = validate_connector(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
