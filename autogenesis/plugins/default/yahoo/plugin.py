"""Yahoo Finance plugin.

Reads Yahoo's public chart endpoint over plain HTTP (``httpx``) — no
``yfinance`` dependency. Returns the canonical Response envelope with
``data = {"symbol", "records": [...], "count"}`` so a downstream ``process``
step can clean it and a ``benchmark`` step can evaluate it.
"""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.history import YahooHistoryTool


@PLUGIN.register_module(force=True)
class YahooPlugin(Plugin):
    """Yahoo Finance — market data for a ticker symbol."""

    tools = (YahooHistoryTool,)

    name: str = "yahoo"
    display_name: str = "Yahoo Finance"
    description: str = "Fetch market data (OHLCV price history) from Yahoo Finance."
    category: str = "data"
    type: str = "data_source"
    instruction: str = (
        "## Provider\nYahoo Finance price history.\n\n"
        "## Parameters\n"
        "- symbol (str): ticker, e.g. ``AAPL`` (required).\n"
        "- range (str): time span — 1d/5d/1mo/3mo/6mo/1y/2y/5y/max (default ``1mo``).\n"
        "- interval (str): candle interval — 1m/5m/1h/1d/1wk/1mo (default ``1d``).\n\n"
        "## Output\n``data.records`` = list of {date, open, high, low, close, adj_close, volume}."
    )
