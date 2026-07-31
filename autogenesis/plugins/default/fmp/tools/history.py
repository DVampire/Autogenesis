"""Financial Modeling Prep OHLCV price history."""

from typing import Any, Dict, List

from autogenesis.plugins.types import PluginTool
from autogenesis.response.types import Response

_HISTORY_URL = "https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Autogenesis data-source plugin)"}


class FMPHistoryTool(PluginTool):
    """Daily OHLCV price history for a ticker symbol."""

    name: str = "history"
    display_name: str = "FMP History"
    description: str = "Fetch daily OHLCV price history for a ticker symbol from Financial Modeling Prep."
    type: str = "data_source"

    async def __call__(self, symbol: str = "", api_key: str = "", limit: int = 30,
                       timeout: float = 30.0, **kwargs) -> Response:
        import httpx

        symbol = str(symbol or kwargs.get("ticker") or "").strip().upper()
        if not symbol:
            return self._fail(f"{self.id}: 'symbol' is required.")
        key = self._secret(api_key, "FMP_API_KEY")
        if not key:
            return self._fail(f"{self.id}: no api key (set api_key / FMP_API_KEY; 'demo' works for AAPL).")

        try:
            limit = max(1, int(limit))
        except (TypeError, ValueError):
            limit = 30

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS, follow_redirects=True) as client:
                response = await client.get(_HISTORY_URL.format(symbol=symbol),
                                            params={"apikey": key, "timeseries": limit})
        except Exception as exc:  # noqa: BLE001 — network failure is a failed result
            return self._fail(f"{self.id}: request failed: {exc}")

        if response.status_code >= 400:
            return self._fail(f"{self.id}: HTTP {response.status_code} for {symbol}: {response.text[:300]}")

        payload = response.json()
        historical = payload.get("historical") if isinstance(payload, dict) else None
        if not historical:
            return self._fail(f"{self.id}: no data for {symbol} (check symbol/key).")

        records: List[Dict[str, Any]] = [{
            "date": row.get("date"),
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "adj_close": row.get("adjClose"),
            "volume": row.get("volume"),
        } for row in historical if isinstance(row, dict)]
        # FMP returns newest-first; normalize to oldest-first like Yahoo.
        records.reverse()

        return self._ok(f"Fetched {len(records)} daily candles for {symbol} from FMP.",
                        symbol=symbol, records=records, count=len(records))
