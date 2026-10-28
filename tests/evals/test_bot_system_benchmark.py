"""Benchmark receipts must retain failed admissions and reject missing cases."""

import json
import subprocess
import sys

import pytest

from evals.bot_system_benchmark import run as bench


def test_checkpoint_retains_unfinished_and_failed_launches(tmp_path):
    path = tmp_path / "receipts.json"
    report = {
        "discovery": [{"arm": "hermes", "status": "running"}],
        "queue": [],
        "expected_launches": 8,
        "run_status": "running",
    }
    bench.checkpoint(path, report)
    saved = json.loads(path.read_text())
    assert saved["launches"] == 1 and saved["completed_launches"] == 0
    assert saved["discovery"][0]["status"] == "running"

    report["discovery"][0]["status"] = "timeout"
    report["queue"].append({"arm": "openbot", "status": "completed"})
    bench.checkpoint(path, report)
    saved = json.loads(path.read_text())
    assert saved["launches"] == 2 and saved["completed_launches"] == 1
    assert saved["discovery"][0]["status"] == "timeout"
    assert saved["expected_launches"] == 8 and saved["run_status"] == "running"


def test_invoke_provisions_the_isolated_profile_and_excludes_credentials(monkeypatch):
    monkeypatch.setenv("BENCHMARK_FAKE_API_KEY", "fixture-only")
    command = [
        sys.executable,
        "-c",
        (
            "import json, os; from pathlib import Path; "
            "print(json.dumps({'profile_exists': Path(os.environ['HERMES_HOME']).is_dir(), "
            "'credential_inherited': 'BENCHMARK_FAKE_API_KEY' in os.environ}))"
        ),
    ]
    result = bench.invoke(command)
    assert result["status"] == "completed"
    assert result["data"] == {"profile_exists": True, "credential_inherited": False}


def test_discovery_score_keeps_misses_and_false_positives_in_denominator():
    cases = [
        {
            "id": "hit",
            "group": "available",
            "query": "create ticket",
            "acceptable": ["support.create"],
            "expect_empty": False,
        },
        {
            "id": "miss",
            "group": "available",
            "query": "read ticket",
            "acceptable": ["support.read"],
            "expect_empty": False,
        },
        {
            "id": "wrong",
            "group": "unavailable",
            "query": "send letter",
            "acceptable": [],
            "expect_empty": True,
        },
    ]
    rows = [
        {
            "query": "create ticket",
            "names": ["support.create"],
            "schema_names": ["support.create"],
            "schemas": {"support.create": {"type": "object"}},
            "latencies_ms": [1, 2],
        },
        {
            "query": "read ticket",
            "names": [],
            "schema_names": [],
            "latencies_ms": [3, 4],
        },
        {
            "query": "send letter",
            "names": ["email.send"],
            "schema_names": [],
            "latencies_ms": [5, 6],
        },
    ]
    schemas = {"support.create": {"type": "object"}}
    result = bench.discovery_score({"results": rows}, cases, schemas)
    assert result["cases"] == 3 and result["passed"] == 1
    assert result["groups"]["available"]["schema_ready"] == 1
    assert result["groups"]["unavailable"]["passed"] == 0
    assert result["p50_ms"] == 3.5 and result["p95_ms"] == 6
    with pytest.raises(ValueError, match="every case"):
        bench.discovery_score({"results": rows[:1]}, cases, schemas)


@pytest.mark.parametrize("sample", [True, float("nan"), float("inf")])
def test_discovery_rejects_invalid_timing_samples(sample):
    with pytest.raises(ValueError, match="timing"):
        bench.validate_result({"names": [], "latencies_ms": [sample]}, {})


def test_discovery_rejects_partial_schemas_and_out_of_range_ranks():
    schema = {"type": "object", "required": ["subject"]}
    with pytest.raises(ValueError, match="altered or truncated"):
        bench.validate_result(
            {
                "names": ["ticket.create"],
                "schema_names": ["ticket.create"],
                "schemas": {"ticket.create": {"type": "object"}},
                "latencies_ms": [1],
            },
            {"ticket.create": schema},
        )
    with pytest.raises(ValueError, match="at most five"):
        bench.validate_result(
            {"names": [f"tool_{index}" for index in range(6)], "latencies_ms": [1]}, {}
        )


def test_queue_score_distinguishes_unsupported_from_pass():
    rows = [{"id": case, "status": "pass"} for case in sorted(bench.QUEUE_CASE_IDS)]
    rows[0]["status"] = "unsupported"
    rows[1]["status"] = "runtime_error"
    result = bench.queue_score({"cases": rows})
    assert result["cases"] == len(rows)
    assert result["pass"] == len(rows) - 2
    assert result["unsupported"] == 1 and result["runtime_error"] == 1
    with pytest.raises(ValueError, match="exactly once"):
        bench.queue_score({"cases": rows[:-1] + [rows[0]]})


def test_source_metadata_detects_staged_changes_and_untracked_inputs(tmp_path):
    def git(*args):
        subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            capture_output=True,
            timeout=10,
        )

    git("init", "-q")
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("first")
    git("add", "artifact.txt")
    git(
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "fixture",
    )
    before = bench.source_metadata(tmp_path, None)
    assert not before["tracked_changes"] and before["untracked_entries"] == 0
    artifact.write_text("second")
    git("add", "artifact.txt")
    (tmp_path / "extra.txt").write_text("untracked")
    after = bench.source_metadata(tmp_path, None)
    assert after["revision"] == before["revision"]
    assert after["tracked_changes"] and after["untracked_entries"] == 1
