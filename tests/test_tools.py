from quant_pulse._core.handler_abc import Outcome
from quant_pulse.context import Context

from quant_mcp.profiles import build_config
from quant_mcp.tools import build_catalog, compute_snapshot


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
