"""Yahoo Finance OHLCV price history."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from autogenesis.plugins.types import PluginTool
from autogenesis.response.types import Response

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo rejects requests without a browser-ish UA (429/empty), so send one.
_HEADERS = {"User-Agent": "Mozilla/5.0 (Autogenesis data-source plugin)"}


class YahooHistoryTool(PluginTool):
    """OHLCV price history for a ticker symbol."""

    name: str = "history"
    display_name: str = "Yahoo Finance History"
    description: str = "Fetch OHLCV price history for a ticker symbol from Yahoo Finance."
    type: str = "data_source"

    async def __call__(self, symbol: str = "", range: str = "1mo", interval: str = "1d",  # noqa: A002
                       timeout: float = 30.0, **kwargs) -> Response:
        import httpx

        symbol = str(symbol or kwargs.get("ticker") or "").strip().upper()
        if not symbol:
            return self._fail(f"{self.id}: 'symbol' is required.")

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS, follow_redirects=True) as client:
                response = await client.get(_CHART_URL.format(symbol=symbol),
                                            params={"range": range, "interval": interval})
        except Exception as exc:  # noqa: BLE001 — network failure is a failed result
            return self._fail(f"{self.id}: request failed: {exc}")

        if response.status_code >= 400:
            return self._fail(f"{self.id}: HTTP {response.status_code} for {symbol}: {response.text[:300]}")

        chart = ((response.json() or {}).get("chart")) or {}
        if chart.get("error"):
            return self._fail(f"{self.id}: {chart['error']}")
        results = chart.get("result") or []
        if not results:
            return self._fail(f"{self.id}: no data for {symbol}.")

        result = results[0]
        timestamps: List[int] = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        adjclose = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []

        records: List[Dict[str, Any]] = [{
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "open": _at(quote.get("open"), i),
            "high": _at(quote.get("high"), i),
            "low": _at(quote.get("low"), i),
            "close": _at(quote.get("close"), i),
            "adj_close": _at(adjclose, i),
            "volume": _at(quote.get("volume"), i),
        } for i, ts in enumerate(timestamps)]

        return self._ok(f"Fetched {len(records)} {interval} candles for {symbol} ({range}).",
                        symbol=symbol, range=range, interval=interval,
                        records=records, count=len(records))


def _at(series, index):
    """Safe indexed access — Yahoo pads gaps with nulls / short arrays."""
    if isinstance(series, list) and index < len(series):
        return series[index]
    return None
