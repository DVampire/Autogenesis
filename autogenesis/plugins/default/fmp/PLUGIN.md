---
id: fmp
name: FMP
category: data
type: data_source
tools: 1
implemented: 1
credentials: [FMP_API_KEY]
requirements: [httpx]
version: "1.0.0"
---
# FMP

Fetch market data (OHLCV price history) from Financial Modeling Prep.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `fmp.history` | FMP History | ✅ | Fetch daily OHLCV price history for a ticker symbol from Financial Modeling Prep. |

All 1 tools are implemented.

## Credentials

`FMP_API_KEY`, an `api_key` argument on the call, or a `fmp_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
