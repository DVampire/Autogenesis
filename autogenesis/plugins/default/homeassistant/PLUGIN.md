---
id: homeassistant
name: Home Assistant
category: data
type: tool
icon: resources/icon.svg
tools: 2
implemented: 2
credentials: [HA_TOKEN, HOMEASSISTANT_TOKEN]
requirements: [httpx]
version: "1.0.0"
---
# Home Assistant

Home Assistant tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `homeassistant.home_assistant_control` | Home Assistant Control | ✅ | Home Assistant Control |
| `homeassistant.list_home_assistant_states` | List Home Assistant States | ✅ | List Home Assistant States |

All 2 tools are implemented.

## Credentials

`HA_TOKEN`, `HOMEASSISTANT_TOKEN`, an `api_key` argument on the call, or a `homeassistant_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
