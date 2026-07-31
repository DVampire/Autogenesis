"""Financial Modeling Prep plugin.

REST price history, api-keyed. Returns the canonical Response envelope with
``data = {"symbol", "records": [...], "count"}``, normalised oldest-first so it
is interchangeable with Yahoo's output in a data pipeline.
"""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.history import FMPHistoryTool


@PLUGIN.register_module(force=True)
class FMPPlugin(Plugin):
    """Financial Modeling Prep — market data for a ticker symbol."""

    tools = (FMPHistoryTool,)

    name: str = "fmp"
    display_name: str = "FMP"
    description: str = "Fetch market data (OHLCV price history) from Financial Modeling Prep."
    category: str = "data"
    type: str = "data_source"
    instruction: str = (
        "## Provider\nFinancial Modeling Prep price history (REST, api-keyed).\n\n"
        "## Parameters\n"
        "- symbol (str): ticker, e.g. ``AAPL`` (required).\n"
        "- api_key (str): FMP api key; falls back to config/``FMP_API_KEY``. Public ``demo`` works for AAPL.\n"
        "- limit (int): most-recent N candles (default 30).\n\n"
        "## Output\n``data.records`` = list of {date, open, high, low, close, adj_close, volume}."
    )
