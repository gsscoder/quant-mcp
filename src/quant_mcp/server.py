"""
quant-mcp server process.

Builds a single, warm quant_pulse.Context at startup and binds an MCP
server to it over streamable HTTP on localhost. The long-lived process is
what keeps quant-pulse's OHLCV TTL cache warm across requests, unlike a
stdio server spawned per session.
"""

from mcp.server.fastmcp import FastMCP
from quant_pulse.context import Context

from quant_mcp.profiles import build_config
from quant_mcp.tools import build_catalog, compute_snapshot

_config = build_config()
context = Context.from_dict(_config)

mcp = FastMCP("quant-mcp", host="127.0.0.1", port=8000)


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


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
