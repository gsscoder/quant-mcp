"""
Signal profile catalog for quant-mcp.

Per project decision, profiles are baked into quant-mcp in code (not
YAML/env): this module is the single source of truth for which signal
profiles exist, which venue backs each one, and how the underlying
quant-pulse services are wired together.

Venues: every spot venue quant-pulse's ConfigBuilder supports out of the
box (Hyperliquid, Binance spot, Kraken spot) gets the same rsi/atr/
supertrend trio, so no venue is a second-class citizen in the catalog.
Binance's USDT-margined futures client is not wired here (a distinct
market from spot, not a distinct exchange) — add it as its own venue
key if a future profile needs it.
"""

from quant_pulse.builder import ConfigBuilder

_CACHE_MANAGER = "cache_manager"

# One entry per venue: (client-builder method name, client service name).
_VENUES = {
    "hyperliquid": ("hyperliquid_client", "hyperliquid_client"),
    "binance": ("binance_spot_client", "binance_spot_client"),
    "kraken": ("kraken_spot_client", "kraken_spot_client"),
}


def build_config() -> dict:
    """
    Build the quant-pulse config dict backing this server's signal catalog.

    Returns:
        Config dict ready for quant_pulse.context.Context.from_dict()
    """
    builder = ConfigBuilder().cache_manager(_CACHE_MANAGER)
    # No real exchange needed: offline/test profile.
    builder.signal("hello", "hello_signal", mood="happy")

    for venue, (client_method, client_name) in _VENUES.items():
        getattr(builder, client_method)(client_name)
        ohlcv_service = f"{venue}_ohlcv"
        builder.ohlcv(ohlcv_service, using=[client_name, _CACHE_MANAGER])

        builder.signal(f"markets_{venue}", "market_volume_signal", exchange_service=client_name)

        atr_profile = f"atr_{venue}"
        builder.signal(f"rsi_{venue}", "rsi_signal", ohlcv_service=ohlcv_service)
        builder.signal(atr_profile, "atr_signal", ohlcv_service=ohlcv_service)
        builder.signal(
            f"supertrend_{venue}",
            "supertrend_signal",
            ohlcv_service=ohlcv_service,
            atr_signal=atr_profile,
        )

    return builder.build()
