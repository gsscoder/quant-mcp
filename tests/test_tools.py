import pytest

from quant_pulse._core.handler_abc import Outcome
from quant_pulse.context import Context

from quant_mcp.profiles import build_config
from quant_mcp.tools import build_catalog, compute_snapshot, list_markets


def test_list_signals_catalog_includes_hello_profile():
    config = build_config()
    context = Context.from_dict(config)
    try:
        catalog = build_catalog(context, config)
    finally:
        context.close()

    entries = {entry["profile"]: entry for entry in catalog}
    assert "hello" in entries

    hello = entries["hello"]
    assert hello["venue"] is None

    assert isinstance(hello["tells"], str)
    assert hello["tells"] != ""

    assert isinstance(hello["ops"], dict)
    assert isinstance(hello["returns"], dict)


def test_list_signals_catalog_derives_venue_for_markets_profiles_from_exchange_service():
    # REQ: _derive_venue also resolves venue from a profile's 'exchange_service' config key
    # (not just 'ohlcv_service'), so markets_* profiles show a populated venue, not None.
    config = build_config()
    context = Context.from_dict(config)
    try:
        catalog = build_catalog(context, config)
    finally:
        context.close()

    entries = {entry["profile"]: entry for entry in catalog}
    for venue in ("kraken", "binance", "hyperliquid"):
        profile_name = f"markets_{venue}"
        assert profile_name in entries
        assert entries[profile_name]["venue"] == venue


def test_get_snapshot_fan_out_produces_one_cell_per_target_selection_pair():
    config = build_config()
    context = Context.from_dict(config)
    try:
        selections = [{"profile": "hello", "op": "greet", "request": {"subject": "Ada"}}]
        snapshot = compute_snapshot(context, config, ["test", "smpl"], selections)
    finally:
        context.close()

    cells = snapshot["snapshot"]
    assert len(cells) == 2
    assert {cell["target"] for cell in cells} == {"test", "smpl"}
    for cell in cells:
        assert cell["error"] is None
        assert cell["result"] == "HAPPY_GREET"
        assert cell["computed_at"] is not None


def test_get_snapshot_isolates_a_failing_cell_from_its_siblings():
    config = build_config()
    context = Context.from_dict(config)
    try:
        selections = [{"profile": "hello", "op": "greet", "request": {"subject": "Ada"}}]
        # 'bogus' isn't a target hello_signal supports -> that cell errors, 'test' still succeeds.
        snapshot = compute_snapshot(context, config, ["test", "bogus"], selections)
    finally:
        context.close()

    cells = {cell["target"]: cell for cell in snapshot["snapshot"]}
    assert cells["test"]["error"] is None
    assert cells["test"]["result"] == "HAPPY_GREET"
    assert cells["bogus"]["error"] is not None
    assert cells["bogus"]["result"] is None


def test_get_snapshot_unknown_profile_lists_valid_profile_names():
    config = build_config()
    context = Context.from_dict(config)
    try:
        selections = [{"profile": "not_a_real_profile", "op": "greet", "request": {}}]
        snapshot = compute_snapshot(context, config, ["test"], selections)
    finally:
        context.close()

    cell = snapshot["snapshot"][0]
    assert cell["result"] is None
    assert cell["error"] is not None
    for profile_name in config["signals"]:
        assert profile_name in cell["error"]


class _FakeProxy:
    """Stand-in for _SignalProxy: skips Context/handler wiring entirely."""

    def __init__(self, result: dict):
        self._result = result

    def compute_signal(self, target, signal_op, request):
        return Outcome(result=self._result, computation="fake", computed_at="2026-08-10T00:00:00.000000Z")


class _FakeContext:
    """Stand-in for Context, boundary-mocked so no real signal/network call happens."""

    def __init__(self, result: dict):
        self._result = result

    def get_signal_handler(self, profile_name):
        return _FakeProxy(self._result)


def test_get_snapshot_include_series_toggles_full_array_fields():
    config = build_config()
    rsi_like_result = {"symbol": "BTC", "latest_rsi": 55.0, "rsi": [40.0, 45.0, 55.0], "regime": "neutral"}
    context = _FakeContext(rsi_like_result)
    selection = [{"profile": "rsi_hyperliquid", "op": "compute_rsi", "request": {"period": 14, "timeframe": "1h"}}]

    lean = compute_snapshot(context, config, ["BTC"], selection, include_series=False)
    lean_result = lean["snapshot"][0]["result"]
    assert "rsi" not in lean_result
    assert lean_result["latest_rsi"] == 55.0
    assert lean_result["regime"] == "neutral"

    full = compute_snapshot(context, config, ["BTC"], selection, include_series=True)
    full_result = full["snapshot"][0]["result"]
    assert full_result["rsi"] == [40.0, 45.0, 55.0]


def test_list_markets_unknown_venue_returns_error_without_raising():
    # REQ: list_markets never raises on a bad venue; it reports the valid venue list instead.
    config = build_config()
    context = Context.from_dict(config)
    try:
        result = list_markets(context, config, "nonexistent")
    finally:
        context.close()

    assert result["venue"] == "nonexistent"
    assert result["markets"] is None
    assert result["computed_at"] is None
    assert "kraken" in result["error"]
    assert "binance" in result["error"]
    assert "hyperliquid" in result["error"]


class _FakeMarketsProxy:
    """Stand-in for _SignalProxy: skips Context/handler wiring, records the request it received."""

    def __init__(self, result: dict):
        self._result = result
        self.last_request = None

    def compute_signal(self, target, signal_op, request):
        self.last_request = request
        return Outcome(result=self._result, computation="fake", computed_at="2026-08-10T00:00:00.000000Z")


class _FakeMarketsContext:
    """Stand-in for Context: boundary-mocked so no real exchange client call happens, records the profile asked for."""

    def __init__(self, result: dict):
        self.proxy = _FakeMarketsProxy(result)
        self.requested_profiles = []

    def get_signal_handler(self, profile_name):
        self.requested_profiles.append(profile_name)
        return self.proxy


_SAMPLE_MARKETS_RESULT = {
    "exchange": "kraken",
    "quote": None,
    "count": 2,
    "markets": [
        {"symbol": "BTC/USD", "quote_volume_24h": 200.0, "quote": "USD"},
        {"symbol": "ETH/USD", "quote_volume_24h": 100.0, "quote": "USD"},
    ],
}


def test_list_markets_venue_matching_is_case_insensitive():
    # REQ: venue is matched case-insensitively against 'markets_<venue>' profile names.
    config = build_config()
    context = _FakeMarketsContext(_SAMPLE_MARKETS_RESULT)

    result = list_markets(context, config, "Kraken")

    assert context.requested_profiles == ["markets_kraken"]
    assert result["error"] is None
    assert result["exchange"] == "kraken"


def test_list_markets_happy_path_returns_full_markets_list_not_stripped():
    # REQ: list_markets must never strip 'markets' via _lean_result - the payload's whole purpose is the list.
    config = build_config()
    context = _FakeMarketsContext(_SAMPLE_MARKETS_RESULT)

    result = list_markets(context, config, "kraken")

    assert result["error"] is None
    assert result["computed_at"] == "2026-08-10T00:00:00.000000Z"
    assert isinstance(result["markets"], list)
    assert len(result["markets"]) > 0
    assert result["markets"] == _SAMPLE_MARKETS_RESULT["markets"]


def test_list_markets_top_param_flows_through_to_request():
    # REQ: the 'top' argument is forwarded unmodified in the request dict passed to compute_signal.
    config = build_config()
    context = _FakeMarketsContext(_SAMPLE_MARKETS_RESULT)

    list_markets(context, config, "kraken", top=5)

    assert context.proxy.last_request == {"top": 5}


@pytest.mark.skip(reason="requires live network access to Kraken's public API")
def test_list_markets_live_kraken_returns_real_markets():
    # Integration smoke test against the real Kraken exchange client - not run in CI.
    config = build_config()
    context = Context.from_dict(config)
    try:
        result = list_markets(context, config, "kraken", quote="USD", top=10)
    finally:
        context.close()

    assert result["error"] is None
    assert result["markets"]
    assert len(result["markets"]) <= 10
