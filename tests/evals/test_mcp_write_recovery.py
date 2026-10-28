"""An actual local MCP server commits a side effect before replying."""

import pytest

from evals.bot_system_benchmark.mcp_write_recovery import run_case


@pytest.mark.parametrize("mode", ["invalid_reply", "success"])
def test_real_mcp_write_reply_contract(mode, tmp_path):
    result = run_case(mode, tmp_path)
    assert result["pass"], result
