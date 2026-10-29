"""Separate, authored quality contracts; historical task oracles stay unchanged."""

import csv
import hashlib
import io
import json
from pathlib import Path

TOOLSETS = ["file", "todo"]
CASES = ("orders_reconciliation", "capability_notes")
INPUTS = {
    "orders_reconciliation": {
        "orders.csv": "id,status,cents\nr9,paid,1800\nr2,pending,2000\nr7,paid,-300\nr9,paid,1800\nr4,paid,900\n",
    },
    "capability_notes": {
        "facts.json": '{"cache":{"persistent":false,"ttl_seconds":90},"delivery":{"exactly_once":false,"max_attempts":2}}\n',
        "NOTES.md": "# Existing notes\n" + "Background detail, not a capability guarantee.\n" * 150
        + "The cache survives restarts. Every delivery happens exactly once.\n",
    },
}
PROMPTS = {
    "orders_reconciliation": "Read orders.csv. Keep the first occurrence of each id, include only paid rows, and include negative cents as signed amounts. Create summary.json with exactly integer paid_count and total_cents; paid.csv with header id,cents and the selected rows in source order; checks.json with exactly integer input_rows, unique_ids, duplicate_rows and excluded_unpaid; and README.md explaining how the totals were computed. Preserve orders.csv. Check all four saved deliverables and keep their explanations consistent with the data.",
    "capability_notes": "Read facts.json and NOTES.md. Correct the existing notes using only the stated facts, removing unsupported persistence and delivery guarantees. Write claims.json with exactly cache_persistent, ttl_seconds, exactly_once and max_attempts, retaining the source JSON types. Explain the limits in NOTES.md, including the delivery retry limit. Preserve facts.json. Verify the saved JSON and the factual statements in the saved notes before finishing.",
}


def seed(workspace: Path, case: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    for name, content in INPUTS[case].items():
        (workspace / name).write_text(content, encoding="utf-8")


def _exact(actual, expected) -> bool:
    return (type(actual) is dict and actual.keys() == expected.keys()
            and all(type(actual[k]) is type(v) and actual[k] == v for k, v in expected.items()))


def grade(workspace: Path, case: str) -> dict:
    read = lambda name: (workspace / name).read_text(encoding="utf-8")
    try:
        if case == "orders_reconciliation":
            checks = {
                "summary": _exact(json.loads(read("summary.json")), {"paid_count": 3, "total_cents": 2400}),
                "rows_and_header": list(csv.reader(io.StringIO(read("paid.csv")))) == [["id", "cents"], ["r9", "1800"], ["r7", "-300"], ["r4", "900"]],
                "reconciliation": _exact(json.loads(read("checks.json")), {"input_rows": 5, "unique_ids": 4, "duplicate_rows": 1, "excluded_unpaid": 1}),
                "input_preserved": read("orders.csv") == INPUTS[case]["orders.csv"],
                "note_present": bool(read("README.md").strip()),
            }
        else:
            checks = {
                "typed_claims": _exact(json.loads(read("claims.json")), {"cache_persistent": False, "ttl_seconds": 90, "exactly_once": False, "max_attempts": 2}),
                "facts_preserved": read("facts.json") == INPUTS[case]["facts.json"],
                "notes_updated": bool(read("NOTES.md").strip()) and read("NOTES.md") != INPUTS[case]["NOTES.md"],
            }
        error = None
    except (OSError, ValueError) as exc:
        checks, error = {}, type(exc).__name__
    artifacts = {}
    for path in sorted(workspace.glob("*")):
        if path.is_file():
            raw = path.read_bytes()
            artifacts[path.name] = {"sha256": hashlib.sha256(raw).hexdigest(), "text": raw.decode("utf-8", errors="replace")}
    return {"contract_pass": bool(checks) and all(checks.values()), "checks": checks,
            "grading_error": error, "artifacts": artifacts,
            "prose_review": "Requires a separate unblinded semantic review; file-contract success does not certify every sentence."}
