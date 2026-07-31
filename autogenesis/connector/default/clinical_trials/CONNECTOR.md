---
name: clinical_trials_connector
description: ClinicalTrials.gov (API v2) — search and analyze FDA-regulated clinical studies by condition, intervention, sponsor, investigator, eligibility, and endpoints.
version: 1.0.0
type: worker
permission_mode: read_only
featured: true
connection:
  transport: streamable_http
  url: https://hcls.mcp.claude.com/clinical_trials/mcp
actions:
  - search_trials
  - get_trial_details
  - search_by_sponsor
  - search_investigators
  - analyze_endpoints
  - search_by_eligibility
---

# Clinical Trials

An MCP connector for the NIH/NLM ClinicalTrials.gov registry of FDA-regulated clinical
studies worldwide. Supports competitive/pipeline analysis, patient-trial matching,
investigator site selection, and protocol/endpoint research.

## Tools

### search_trials
Find trials by condition, intervention, location, or status. Primary discovery tool.

### get_trial_details
Deep dive into a specific trial's protocol, endpoints, and locations.

### search_by_sponsor
Company/institution pipeline analysis and competitive intelligence.

### search_investigators
Find principal investigators and research sites for a condition/location.

### analyze_endpoints
Systematically compare outcome measures across trials, for protocol/benchmark analysis.

### search_by_eligibility
Match patients to trials based on demographic and clinical criteria.

## Typical workflow

1. `search_trials` to find relevant trials by condition/intervention.
2. `get_trial_details` for each trial needing deeper analysis.
3. `analyze_endpoints` to compare outcome measures across similar trials.
4. `search_investigators` to identify key opinion leaders and active sites.
