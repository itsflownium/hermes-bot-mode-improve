"""Quality contracts reject wrong arithmetic, missing headers, and bool/int swaps."""

import json

from evals.bot_system_benchmark.quality_tasks import grade, seed


def test_reconciliation_rejects_duplicate_counting_missing_header_and_input_edits(tmp_path):
    seed(tmp_path, "orders_reconciliation")
    (tmp_path / "summary.json").write_text('{"paid_count":3,"total_cents":2400}')
    (tmp_path / "checks.json").write_text('{"input_rows":5,"unique_ids":4,"duplicate_rows":1,"excluded_unpaid":1}')
    (tmp_path / "paid.csv").write_text("id,cents\nr9,1800\nr7,-300\nr4,900\n")
    (tmp_path / "README.md").write_text("Three unique paid rows sum to 2400 cents.")
    assert grade(tmp_path, "orders_reconciliation")["contract_pass"]
    (tmp_path / "summary.json").write_text('{"paid_count":4,"total_cents":4200}')
    assert not grade(tmp_path, "orders_reconciliation")["checks"]["summary"]
    (tmp_path / "paid.csv").write_text("r9,1800\nr7,-300\nr4,900\n")
    assert not grade(tmp_path, "orders_reconciliation")["checks"]["rows_and_header"]
    (tmp_path / "orders.csv").write_text("replacement")
    assert not grade(tmp_path, "orders_reconciliation")["checks"]["input_preserved"]


def test_capability_contract_checks_types_and_retains_the_notes_for_semantic_review(tmp_path):
    seed(tmp_path, "capability_notes")
    claims = {"cache_persistent": False, "ttl_seconds": 90, "exactly_once": False, "max_attempts": 2}
    (tmp_path / "claims.json").write_text(json.dumps(claims))
    (tmp_path / "NOTES.md").write_text("Cache is temporary; deliveries can repeat, up to two attempts.")
    assert grade(tmp_path, "capability_notes")["contract_pass"]
    claims["cache_persistent"] = 0
    (tmp_path / "claims.json").write_text(json.dumps(claims))
    result = grade(tmp_path, "capability_notes")
    assert not result["checks"]["typed_claims"]
    assert result["artifacts"]["NOTES.md"]["text"]


def test_missing_outputs_are_a_failure_with_the_observed_artifacts_retained(tmp_path):
    seed(tmp_path, "capability_notes")
    result = grade(tmp_path, "capability_notes")
    assert not result["contract_pass"]
    assert result["grading_error"] == "FileNotFoundError"
    assert "facts.json" in result["artifacts"]
