# Quant MCP

Quant MCP gives an AI agent market vision through the MCP protocol: a catalog of available market signals, plus on-demand snapshots computed over them. Under the hood it's a thin MCP surface wrapped around [quant-pulse](https://github.com/gsscoder/quant-pulse) library.

Current Version: **0.1.9 (alpha)**

## Core Principles

- Read-only by design: the server perceives markets but never trades. Order execution is left to a separate, dedicated MCP server.

- Venue-agnostic: exchanges and signal profiles live in quant-pulse config, not hardcoded into tool logic.

## Design Goals

- Hand the agent a **catalog** of what it can ask for (kind, venue, ops, params, result shape), fetched once per session so it chooses from real options instead of guessing.

- Compute **snapshots** in batch: N targets across M signal profiles in a single call, one fan-out, result-or-error per cell, so a single dead symbol can't blind the rest.

- Keep things **lean by default**, returning only latest values and regime fields; full series stay opt-in to keep agent context affordable.

## Non-Goals

- No order execution, no position management, no write path into a market at all.

- Not meant as a general-purpose data warehouse; it surfaces only what quant-pulse's signal handlers expose.

## Further Notes

- The codebase is still under active development, so backward compatibility isn't guaranteed when existing features change.

## Installation

```sh
pip install quant-mcp
```

Needs Python 3.11+ and a `quant-pulse` install, which in turn pulls in [TA-Lib](https://ta-lib.org/install/) as a native dependency.

**Tools:**

- `list_signals`: catalog of every configured signal profile — venue, ops, params, result shape, and a one-line statement of what it tells
- `get_snapshot`: batch-compute a signal snapshot across targets x profile selections in one call
- `list_markets`: tradeable markets on a venue, ranked by 24h quote volume, ready to feed back into `get_snapshot` targets

## Usage

Start the server (streamable HTTP on `127.0.0.1:8000` by default):

```sh
python -m quant_mcp.server --port 8000
```

From there, an AI agent connected to the server only needs a plain-language prompt to trigger its tools — for example:

- "Check BTC, SOL, and ETH on Kraken, and tell me which one looks best for opening a position right now, and in which direction."
- "What's the RSI and Supertrend regime for BTC and ETH on Hyperliquid right now?"
- "List Kraken's top 20 markets by 24h volume, quoted in USD, excluding stablecoin/fiat pairs."

Isolation holds per call: a bad target, an unknown profile, or a venue error surfaces in that cell's or result's `error` field instead of raising and dragging the rest of the batch down with it.

## License

MIT — see [LICENSE](LICENSE).
