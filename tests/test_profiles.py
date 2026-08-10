from quant_pulse.context import Context

from quant_mcp.profiles import build_config


def test_build_config_produces_a_working_context():
    context = Context.from_dict(build_config())
    try:
        assert context.get_signal_handler("hello") is not None
    finally:
        context.close()
