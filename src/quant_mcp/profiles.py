"""
Signal profile catalog for quant-mcp.

Per project decision, profiles are baked into quant-mcp in code (not
YAML/env): this module is the single source of truth for which signal
profiles exist, which venue backs each one, and how the underlying
quant-pulse services are wired together.

Venue choice: Hyperliquid. Its public OHLCV endpoints need no API key,
which keeps this scaffold self-contained; quant-pulse also supports
Binance and Kraken (see quant_pulse.builder.ConfigBuilder) should a
future profile need a different venue.
"""

from quant_pulse.builder import ConfigBuilder

_HYPERLIQUID_CLIENT = "hyperliquid_client"
_CACHE_MANAGER = "cache_manager"
_HYPERLIQUID_OHLCV = "hyperliquid_ohlcv"
_ATR_HYPERLIQUID = "atr_hyperliquid"


def build_config() -> dict:
    """
    Build the quant-pulse config dict backing this server's signal catalog.

    Returns:
        Config dict ready for quant_pulse.context.Context.from_dict()
    """
    builder = (
        ConfigBuilder()
        .cache_manager(_CACHE_MANAGER)
        .hyperliquid_client(_HYPERLIQUID_CLIENT)
        .ohlcv(_HYPERLIQUID_OHLCV, using=[_HYPERLIQUID_CLIENT, _CACHE_MANAGER])
        # No real exchange needed: offline/test profile.
        .signal("hello", "hello_signal", mood="happy")
        .signal("rsi_hyperliquid", "rsi_signal", ohlcv_service=_HYPERLIQUID_OHLCV)
        .signal(_ATR_HYPERLIQUID, "atr_signal", ohlcv_service=_HYPERLIQUID_OHLCV)
        .signal(
            "supertrend_hyperliquid",
            "supertrend_signal",
            ohlcv_service=_HYPERLIQUID_OHLCV,
            atr_signal=_ATR_HYPERLIQUID,
        )
    )
    return builder.build()
