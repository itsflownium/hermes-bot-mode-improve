"""Real local-file probes and an oracle that does not trust a 'done' claim."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from evals.bot_system_benchmark.task_backend import grade

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "case", ["complete_files", "status_only", "write_error_recovery"]
)
def test_real_hermes_file_contracts(case, tmp_path):
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "evals/bot_system_benchmark/task_backend.py"),
            "--worker",
            "--arm",
            "hermes",
            "--case",
            case,
            "--hermes",
            str(ROOT),
            "--openbot",
            str(tmp_path),
            "--bun",
            sys.executable,
            "--pi",
            sys.executable,
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    encoded = next(
        line.split("=", 1)[1]
        for line in process.stdout.splitlines()
        if line.startswith("MATCHED_BACKEND_RESULT=")
    )
    result = json.loads(encoded)
    assert result["setup_errors"] == []
    assert result["contract_pass"], result


def test_completion_claim_does_not_substitute_for_the_second_artifact():
    actual = {"report.txt": "REPORT", "attachment.txt": None}
    assert (
        grade("premature_final", actual, "All deliverables are done.", [])[
            "contract_pass"
        ]
        is False
    )
    actual["attachment.txt"] = "ATTACHMENT"
    assert grade("premature_final", actual, "Done.", [])["contract_pass"] is True
