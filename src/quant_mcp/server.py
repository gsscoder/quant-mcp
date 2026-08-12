"""
quant-mcp server process.

Builds a single, warm quant_pulse.Context at startup and binds an MCP
server to it over streamable HTTP on localhost. The long-lived process is
what keeps quant-pulse's OHLCV TTL cache warm across requests, unlike a
stdio server spawned per session.
"""

import argparse

from mcp.server.fastmcp import FastMCP
from quant_pulse.context import Context

from quant_mcp import tools
from quant_mcp.profiles import build_config
from quant_mcp.tools import build_catalog, compute_snapshot

_config = build_config()
context = Context.from_dict(_config)


def _parse_port() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args().port


mcp = FastMCP("quant-mcp", host="127.0.0.1", port=_parse_port())


@mcp.tool()
def list_signals() -> list[dict]:
    """Catalog of configured signal profiles: venue, ops, params, and what each tells you."""
    return build_catalog(context, _config)


@mcp.tool()
def get_snapshot(targets: list[str], selections: list[dict], include_series: bool = False) -> dict:
    """
    Compute a batch of signal snapshots: every target x every selection, one cell each.

    Each selection is {'profile': str, 'op': str, 'request': dict}. One cell
    failing (bad target, unknown profile, computation error) never blocks
    the others. Set include_series=True to get full series instead of just
    latest/regime fields.
    """
    return compute_snapshot(context, _config, targets, selections, include_series)


@mcp.tool()
def list_markets(venue: str, quote: str = "*", top: int = 100) -> dict:
    """
    Tradeable markets on a venue, richest first by 24h quote volume.

    quote is the venue-native quote code ('ZUSD' on Kraken, 'USDT' on
    Binance, 'USD' on Hyperliquid); '*' returns every market. Returned
    symbols feed straight back into get_snapshot targets for that same
    venue. top=-1 removes the cap. Volumes compare within one venue only,
    not across venues.
    """
    return tools.list_markets(context, _config, venue, quote, top)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
