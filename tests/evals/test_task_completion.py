"""Whole agent loop and real local files, with a scripted HTTP model boundary."""

import os
from pathlib import Path

import pytest

from evals.bot_system_benchmark.task_completion import CASES, run_case


@pytest.mark.parametrize("case", CASES)
def test_task_completion_contracts(case, tmp_path):
    result = run_case(case, Path(os.environ["HERMES_HOME"]), tmp_path / "workspace")
    assert result["pass"], result
    assert result["prefix_stable"], result
    assert result["tool_surface_stable"], result
    if case == "premature_final":
        assert result["resume"] == {"request_count": 1, "written_this_turn": False}
        assert result["checklist"]["completion_verified"] is False
