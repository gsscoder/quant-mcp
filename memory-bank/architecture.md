# Architecture
Thin MCP surface over a single warm `quant_pulse.Context`; two tools, no persistence, no auth, no config files

## Package Layout
`src/quant_mcp/`:
- `server.py` — process entry point: builds the module-level `Context`, constructs `FastMCP`, declares `list_signals`/`get_snapshot` as thin wrappers over `tools.py`, `main()`
- `profiles.py` — the signal catalog as code: `build_config() -> dict`, one `ConfigBuilder` chain wiring services + the four signal profiles
- `tools.py` — both tools' real logic: `build_catalog()` (`list_signals`) and `compute_snapshot()` (`get_snapshot`), plus their private helpers
- `__init__.py` — empty

No config files, no env-var loading, no persistence layer, no auth module anywhere in the package.

## Context Lifecycle
`server.py` module top level (runs once, at import):
```python
_config = build_config()
context = Context.from_dict(_config)
mcp = FastMCP("quant-mcp", host="127.0.0.1", port=8000)
```
`context` is a single process-lifetime object, built before `FastMCP` even exists, and both tool functions close over it as a module global — every `list_signals`/`get_snapshot` call across every client session reuses the same `Context`. Per the module docstring this is deliberate: it's what keeps quant-pulse's OHLCV TTL cache warm across requests. A stdio MCP server spawned fresh per client session would rebuild `Context` (and cold the cache) every session; `streamable-http` with one long-lived process avoids that.
Nothing in `quant_mcp` ever calls `context.close()` — tests close their own locally-built `Context` in a `finally`, but the module-level one in `server.py` lives until process exit.

## Profile Model
`profiles.py::build_config() -> dict` returns the raw quant-pulse config dict (`{"services": {...}, "signals": {...}}`) passed straight into `Context.from_dict()`. Built via `quant_pulse.builder.ConfigBuilder`:
```python
ConfigBuilder()
    .cache_manager(_CACHE_MANAGER)
    .hyperliquid_client(_HYPERLIQUID_CLIENT)
    .ohlcv(_HYPERLIQUID_OHLCV, using=[_HYPERLIQUID_CLIENT, _CACHE_MANAGER])
    .signal("hello", "hello_signal", mood="happy")
    .signal("rsi_hyperliquid", "rsi_signal", ohlcv_service=_HYPERLIQUID_OHLCV)
    .signal(_ATR_HYPERLIQUID, "atr_signal", ohlcv_service=_HYPERLIQUID_OHLCV)
    .signal("supertrend_hyperliquid", "supertrend_signal",
            ohlcv_service=_HYPERLIQUID_OHLCV, atr_signal=_ATR_HYPERLIQUID)
```
Four profiles, exactly:
- `hello` — `hello_signal`, no `ohlcv_service` → offline/test profile, no network, no venue
- `rsi_hyperliquid` — `rsi_signal` over the shared `hyperliquid_ohlcv` service
- `atr_hyperliquid` — `atr_signal` over the same OHLCV service
- `supertrend_hyperliquid` — `supertrend_signal`, depends on both the OHLCV service and the `atr_hyperliquid` profile by name (`atr_signal=_ATR_HYPERLIQUID`) — one profile consuming another's output

Venue: Hyperliquid only, chosen because its public OHLCV endpoints need no API key (module docstring). quant-pulse's `ConfigBuilder` also has Binance/Kraken client methods; unused here, not wired to any profile.
Profiles are baked into this module in code, not YAML/env — an explicit project decision stated in the module docstring, not an oversight to fix later.

## `list_signals`
`server.py`: `list_signals() -> list[dict]`, no arguments, delegates to `tools.build_catalog(context, _config)`.
`tools.py::build_catalog(context: Context, config: dict) -> list[dict]` iterates `config["signals"].items()` and for each profile emits `{"profile", "venue", "tells", "ops", "returns"}`:
- `venue` — `_derive_venue(handler_config, services)`: only set if the profile's config has an `ohlcv_service` key; walks that service's `_using` dependency list looking for a service whose `_service` module path matches `^exchange/(\w+)_client$` (regex `_VENUE_CLIENT_PATTERN`), returns the captured venue name or `None`. Purely config-driven — no hardcoded per-profile venue table.
- `tells`/`ops`/`returns` — read from the handler's own descriptor via `_get_descriptor(context, profile_name)`.

**Design debt, flagged precisely**: `_get_descriptor()` has no public API to call. Its docstring says so outright: "Context/_SignalProxy expose no public descriptor accessor yet (only `compute_signal()` and `get_metadata()`)". The workaround reaches into private attributes:
```python
proxy = context.get_signal_handler(profile_name)
handler = context._handler_registry.get_handler(
    proxy._handler_module_name, proxy._handler_config, context=context
)
try:
    return dict(handler.get_descriptor())
finally:
    handler.__exit__(None, None, None)
```
`_handler_registry`, `proxy._handler_module_name`, `proxy._handler_config` are all `Context`/`_SignalProxy` private attributes, accessed by mirroring what `_SignalProxy.get_metadata()` does internally rather than calling a supported method. This is stable only as long as quant-pulse's private layout doesn't change; it breaks silently (AttributeError) on any quant-pulse internal refactor. Fix is upstream: quant-pulse needs a public descriptor accessor on `Context` or `_SignalProxy`.

## `get_snapshot`
`server.py`: `get_snapshot(targets: list[str], selections: list[dict], include_series: bool = False) -> dict`, delegates to `tools.compute_snapshot(context, _config, targets, selections, include_series)`.
`tools.py::compute_snapshot(context, config, targets, selections, include_series=False) -> dict` — a plain nested loop, `for target in targets: for selection in selections:`, target-major order, producing exactly `len(targets) * len(selections)` cells under `{"snapshot": [...]}`. Each `selection` is `{"profile": str, "op": str, "request": dict}`; each cell is `{"target", "profile", "op", "result", "error", "computed_at"}`.

Per-cell isolation, three independent failure paths, none of which stop the fan-out:
1. **Unknown profile** — `profile not in valid_profiles` (`valid_profiles = sorted(config["signals"].keys())`) short-circuits before any compute call; `error` lists every valid profile name, `computed_at` is `None`.
2. **Compute-time exception** — `context.get_signal_handler(profile).compute_signal(target, op, request)` wrapped in `try/except Exception` (`# noqa: BLE001` — deliberately broad, "per-cell isolation, never let one cell kill the fan-out"); `error = str(exc)`, `computed_at` is `None`.
3. **`Outcome.errors`** — a successful call that still returns handler-level errors (`outcome.errors` truthy) becomes an error cell via `_format_outcome_errors` (`"kind: message"` pairs joined with `"; "`), but here `computed_at = outcome.computed_at` is still populated.

Success path: `result = outcome.result if include_series or not isinstance(outcome.result, dict) else _lean_result(outcome.result)`. `_lean_result()` drops every list-valued key from the result dict — the mechanism that keeps the default payload small without a per-profile field allowlist: any handler that puts its full series under a list-valued key (rsi/atr/supertrend all do) gets it stripped by default, only scalar latest/regime fields survive. `include_series=True` returns `outcome.result` untouched. Non-dict results (e.g. `hello`'s plain string) always pass through unchanged regardless of `include_series`.

**Known limitation, flagged precisely**: `computed_at` on every cell is `outcome.computed_at` as returned by quant-pulse — the wall-clock time the `Outcome` was constructed, not the OHLCV candle's actual close time. quant-pulse's `Outcome` doesn't expose candle-close time today, so `compute_snapshot` has nothing truer to report; a snapshot taken seconds after a candle closes and one taken seconds before the next one produces indistinguishable `computed_at` values.

## Transport
`FastMCP("quant-mcp", host="127.0.0.1", port=8000)`, `mcp.run(transport="streamable-http")` in `main()`. Bound to loopback only, no auth of any kind anywhere in the package — no auth middleware, no token check, no TLS. This is intentional, not an oversight: the server never leaves `127.0.0.1`, so there's no network boundary for auth to protect.

## Dependency Boundary
`pyproject.toml`: `dependencies = ["mcp>=1.29.0,<2.0.0", "quant-pulse>=0.2.0"]`. quant-pulse is consumed as a normal pinned PyPI dependency — a plain version specifier, no path/editable/git source override anywhere in `pyproject.toml`. `quant_mcp` only ever imports quant-pulse's public surface (`quant_pulse.context.Context`, `quant_pulse.builder.ConfigBuilder`) except for the one private-attribute reach-in in `_get_descriptor()` above.

## Test Posture
Two files, `tests/test_profiles.py` (1 test) and `tests/test_tools.py` (5 tests), all synchronous `pytest` functions, no fixtures, no `conftest.py`, no pytest config in `pyproject.toml`.

Coverage:
- `build_config()` produces a `Context` that resolves the `hello` handler (`test_build_config_produces_a_working_context`)
- `build_catalog()` includes `hello` with `venue is None` and correctly shaped `tells`/`ops`/`returns` (`test_list_signals_catalog_includes_hello_profile`)
- `compute_snapshot()` fan-out cardinality (`test_get_snapshot_fan_out_produces_one_cell_per_target_selection_pair`), per-cell error isolation via a target the `hello` handler rejects (`test_get_snapshot_isolates_a_failing_cell_from_its_siblings`), unknown-profile error message content (`test_get_snapshot_unknown_profile_lists_valid_profile_names`)
- `include_series` lean/full toggle (`test_get_snapshot_include_series_toggles_full_array_fields`) — the only test that doesn't touch a real `Context`; it boundary-mocks `Context`/`_SignalProxy` with local `_FakeContext`/`_FakeProxy` classes returning a canned rsi-shaped `Outcome`, specifically to avoid any Hyperliquid network call while still exercising `rsi_hyperliquid`-shaped data

Every other test that runs against a real `Context` only ever calls the `hello` profile, which per `profiles.py` needs no exchange — the whole suite is offline, no HTTP hits any venue.