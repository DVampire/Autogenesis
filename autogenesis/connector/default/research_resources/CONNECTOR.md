---
name: research_resources_connector
description: Research resources — Grants.gov funding opportunity search and Antibody Registry (RRID) antibody lookups. Public APIs, no auth.
version: 1.0.0
type: worker
permission_mode: read_only
featured: true
connection:
  transport: stdio
  command: python
  args:
    - server.py
actions:
  - search_grants
  - search_antibodies
  - get_antibody
  - find_antibodies_by_catalog
  - get_antibody_registry_stats
---

# Research Resources

A self-contained MCP connector for research-support lookups over **public** APIs
(no authentication): **Grants.gov** (federal funding opportunities) and the
**Antibody Registry** (research antibodies / RRIDs).

## Tools

- `search_grants` — search Grants.gov funding opportunities by keyword. Args: `keyword`, `limit`.
- `search_antibodies` — full-text search the Antibody Registry. Args: `query`, `limit`.
- `get_antibody` — antibody details by id/RRID. Args: `antibody_id` (e.g. "3751761" or "AB_2532057").
- `find_antibodies_by_catalog` — find antibodies by vendor catalog number. Args: `catalog_number`, `limit`.
- `get_antibody_registry_stats` — registry totals and last-update date. No args.

## Typical workflow

1. `search_grants` to find funding opportunities relevant to a project.
2. `search_antibodies` / `find_antibodies_by_catalog` to identify a validated antibody and its
   RRID; `get_antibody` for its full record (vendor, clonality, target, citation).

## Notes

- Read-only; hits the public Grants.gov and Antibody Registry APIs, so responses depend on
  their uptime.
- The `connection` uses a relative `server.py` and `command: python`, which the connector manager resolves to absolute paths at load time, so no machine-specific paths are needed.
