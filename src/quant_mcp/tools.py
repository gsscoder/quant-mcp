"""
list_signals tool: the catalog of configured signal profiles.

Builds one catalog entry per signal profile declared in profiles.py,
merging the venue it is wired to (derived from config, not hardcoded)
with the handler's own descriptor (tells/ops/returns).
"""

import re
from typing import Optional

from quant_pulse.context import Context

# Matches the '_service' module path of a venue client service, e.g.
# 'exchange/hyperliquid_client' -> 'hyperliquid'. See ConfigBuilder's
# *_client() methods in quant_pulse.builder.
_VENUE_CLIENT_PATTERN = re.compile(r"^exchange/(\w+)_client$")


def _derive_venue(handler_config: dict, services: dict) -> Optional[str]:
    """
    it mDerive the venue a signal profile is wired to from its config.

    A profile is venue-bound if its handler config references an
    'ohlcv_service' (that service's dependencies are inspected for a venue
    client service, module path 'exchange/<venue>_client'), or if it
    references an 'exchange_service' directly (matched against the venue
    client pattern with no '_using' indirection, since exchange_service
    names the client service itself). Profiles with neither (e.g. 'hello')
    have no venue.

    Args:
        handler_config: Raw signal profile config (e.g. config['signals'][name])
        services: Raw services config (config['services'])
    Returns:
        Venue name (e.g. 'hyperliquid'), or None if the profile isn't venue-bound
    """
    ohlcv_service_name = handler_config.get("ohlcv_service")
    if ohlcv_service_name:
        ohlcv_config = services.get(ohlcv_service_name, {})
        for dep_name in ohlcv_config.get("_using", []):
            match = _VENUE_CLIENT_PATTERN.match(services.get(dep_name, {}).get("_service", ""))
            if match:
                return match.group(1)

    exchange_service_name = handler_config.get("exchange_service")
    if exchange_service_name:
        match = _VENUE_CLIENT_PATTERN.match(services.get(exchange_service_name, {}).get("_service", ""))
        if match:
            return match.group(1)

    return None


def _get_descriptor(context: Context, profile_name: str) -> dict:
    """
    Resolve a profile's handler and read its descriptor.

    Context/_SignalProxy expose no public descriptor accessor yet (only
    compute_signal() and get_metadata()), so this mirrors _SignalProxy's
    own get_metadata() implementation: resolve the handler via the proxy's
    resolved module name/config, instantiate a throwaway handler through
    the context's handler registry, read its descriptor, then dispose it.
    """
    proxy = context.get_signal_handler(profile_name)
    handler = context._handler_registry.get_handler(
        proxy._handler_module_name, proxy._handler_config, context=context
    )
    try:
        return dict(handler.get_descriptor())
    finally:
        handler.__exit__(None, None, None)


def _format_outcome_errors(errors: dict) -> str:
    """Render an Outcome.errors dict (error kind -> message) as one string."""
    return "; ".join(f"{kind}: {message}" for kind, message in errors.items())


def _lean_result(result: dict) -> dict:
    """
    Strip heavy array fields from a handler result dict.

    Every profile so far (rsi/atr/supertrend) puts its full series under a
    list-valued field (e.g. 'rsi', 'atr') alongside scalar latest/regime
    fields; dropping list-valued entries is what keeps the default payload
    lean without hardcoding per-profile field names.
    """
    return {key: value for key, value in result.items() if not isinstance(value, list)}


def compute_snapshot(
    context: Context, config: dict, targets: list[str], selections: list[dict], include_series: bool = False
) -> dict:
    """
    Fan out N targets x M selections into one snapshot cell per pair.

    Each selection is {'profile': str, 'op': str, 'request': dict}. A cell's
    failure (bad target, bad request, unknown profile) is captured on that
    cell only - it never raises or blocks sibling cells.

    Args:
        context: Warm Context built from the same config
        config: Raw config dict as returned by profiles.build_config()
        targets: Symbols/targets to compute each selection over (e.g. ['BTC'])
        selections: Signal profiles/ops/params to compute for every target
        include_series: If False (default), drop full-series array fields from
            each cell's result, keeping only latest/regime-shaped scalars.
            If True, return the handler result unmodified.
    Returns:
        {'snapshot': [{'target', 'profile', 'op', 'result', 'error', 'computed_at'}, ...]}
        with exactly len(targets) * len(selections) cells, in target-major order.
    """
    valid_profiles = sorted(config["signals"].keys())

    cells = []
    for target in targets:
        for selection in selections:
            profile = selection.get("profile")
            op = selection.get("op")
            request = selection.get("request") or {}

            if profile not in valid_profiles:
                cells.append(
                    {
                        "target": target,
                        "profile": profile,
                        "op": op,
                        "result": None,
                        "error": (
                            f"Unknown signal profile '{profile}'. "
                            f"Valid profiles: {', '.join(valid_profiles)}"
                        ),
                        "computed_at": None,
                    }
                )
                continue

            try:
                outcome = context.get_signal_handler(profile).compute_signal(target, op, request)
            except Exception as exc:  # noqa: BLE001 - per-cell isolation, never let one cell kill the fan-out
                cells.append(
                    {
                        "target": target,
                        "profile": profile,
                        "op": op,
                        "result": None,
                        "error": str(exc),
                        "computed_at": None,
                    }
                )
                continue

            if outcome.errors:
                cells.append(
                    {
                        "target": target,
                        "profile": profile,
                        "op": op,
                        "result": None,
                        "error": _format_outcome_errors(outcome.errors),
                        "computed_at": outcome.computed_at,
                    }
                )
                continue

            result = outcome.result if include_series or not isinstance(outcome.result, dict) else _lean_result(outcome.result)
            cells.append(
                {
                    "target": target,
                    "profile": profile,
                    "op": op,
                    "result": result,
                    "error": None,
                    "computed_at": outcome.computed_at,
                }
            )

    return {"snapshot": cells}


def list_markets(context: Context, config: dict, venue: str, quote: str = "*", top: int = 100) -> dict:
    """
    Tradeable markets on a venue, ranked by 24h quote volume.

    venue is matched case-insensitively against the venue names reported
    by list_signals (e.g. 'kraken'). quote is the venue-native quote code
    ('*' = all markets, no normalization). Mirrors compute_snapshot's
    per-call isolation: never raises, returns an 'error' field instead.
    """
    profile = f"markets_{venue.lower()}"
    if profile not in config["signals"]:
        valid = sorted(name[len("markets_"):] for name in config["signals"] if name.startswith("markets_"))
        return {
            "venue": venue, "markets": None,
            "error": f"Unknown venue '{venue}'. Valid venues: {', '.join(valid)}",
            "computed_at": None,
        }

    try:
        outcome = context.get_signal_handler(profile).compute_signal(quote, "list_markets", {"top": top})
    except Exception as exc:  # noqa: BLE001 - never let this raise, mirrors compute_snapshot's per-cell isolation
        return {"venue": venue, "markets": None, "error": str(exc), "computed_at": None}

    if outcome.errors:
        return {
            "venue": venue, "markets": None,
            "error": _format_outcome_errors(outcome.errors),
            "computed_at": outcome.computed_at,
        }

    return {**outcome.result, "error": None, "computed_at": outcome.computed_at}


def build_catalog(context: Context, config: dict) -> list[dict]:
    """
    Build the signal catalog: one entry per configured signal profile.

    Args:
        context: Warm Context built from the same config
        config: Raw config dict as returned by profiles.build_config()
    Returns:
        List of catalog entries, one per profile, each with:
        profile, venue, tells, ops, returns
    """
    signals = config["signals"]
    services = config["services"]

    catalog = []
    for profile_name, handler_config in signals.items():
        descriptor = _get_descriptor(context, profile_name)
        catalog.append(
            {
                "profile": profile_name,
                "venue": _derive_venue(handler_config, services),
                "tells": descriptor["tells"],
                "ops": descriptor["ops"],
                "returns": descriptor["returns"],
            }
        )

    return catalog
