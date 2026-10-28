"""Predeclared local tasks and artifact oracles for actual model-driven turns."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

CASES = (
    "data_summary",
    "config_migration",
    "code_repair",
    "transient_recovery",
    "user_correction",
    "missing_input",
)
OFFLINE = " Work only inside this workspace, without network access, package installation or delegation."
PRECISE_CORRECTION = [
    'Create priorities.json with exactly this root JSON object: {"limit":17,"unit":"minutes"}. Do not add a wrapper, array or other properties.',
    'Correction: change the root limit to 43 and keep the unit minutes. priorities.json must contain exactly {"limit":43,"unit":"minutes"}. Also create CHANGELOG.md recording the change from 17 to 43.',
]
INPUTS = {
    "data_summary": {
        "orders.csv": "id,status,cents\na,paid,1250\nb,pending,900\nc,paid,2750\na,paid,1250\n"
    },
    "config_migration": {
        "settings.json": '{"version":1,"user":{"color":"blue","name":"Ada"},"keep":{"enabled":true}}\n'
    },
    "code_repair": {
        "queue_ops.py": 'def ready(items):\n    return [item["id"] for item in items[:-1] if item.get("status") != "done"]\n',
        "test_queue_ops.py": "import unittest\nfrom queue_ops import ready\nclass QueueTests(unittest.TestCase):\n def test_empty(self): self.assertEqual(ready([]), [])\n def test_last(self): self.assertEqual(ready([{'id':'a','status':'queued'}]), ['a'])\n def test_states(self): self.assertEqual(ready([{'id':'a','status':'running'},{'id':'b','status':'done'},{'id':'c','status':'queued'}]), ['c'])\n def test_order(self): self.assertEqual(ready([{'id':'b','status':'queued'},{'id':'a','status':'queued'}]), ['b','a'])\n def test_missing(self): self.assertEqual(ready([{'id':'a'}]), [])\nif __name__ == '__main__': unittest.main()\n",
    },
    "transient_recovery": {
        "generate_report.py": "from pathlib import Path\nimport sys\np=Path('.attempts')\nn=int(p.read_text())+1 if p.exists() else 1\np.write_text(str(n))\nif n==1:\n print('TRANSIENT_RETRY:75', file=sys.stderr)\n sys.exit(75)\nprint('RECOVERED_TOTAL=42')\n"
    },
    "user_correction": {},
    "missing_input": {},
}
PROMPTS = {
    "data_summary": [
        "Read orders.csv. Deduplicate by id, include only paid orders, and create summary.json with integer fields paid_count and total_cents. Also create paid.csv with columns id,cents, one row per paid order in input order."
    ],
    "config_migration": [
        "Read settings.json and write settings-v2.json: version 2, rename user.color to user.theme, preserve user.name and every unrelated field. Keep the original file unchanged. Write MIGRATION.md explaining color -> theme and version 1 -> 2."
    ],
    "code_repair": [
        "Fix queue_ops.ready so it returns only queued item ids in their original order, including the last item, handles empty input, and excludes missing/other states. Do not modify test_queue_ops.py. Run python -m unittest -q, and save its complete output including stderr to TEST_RESULTS.txt."
    ],
    "transient_recovery": [
        "Run python generate_report.py. The helper can fail with transient exit 75 on its first invocation; retry it exactly once on that exit. Do not edit the helper or .attempts. Save the successful stdout to report.txt, and status.json with attempts: 2 and recovered: true. Stop and explain any other error."
    ],
    "user_correction": [
        "Create priorities.json with limit 17 and unit minutes.",
        "Correction: change the limit to 43; keep the unit minutes. Update priorities.json and create CHANGELOG.md recording the change from 17 to 43.",
    ],
    "missing_input": [
        "Calculate the source.csv total. The source.csv file is missing; do not invent data or create report.json. Instead write BLOCKER.md stating that source.csv is needed with columns date and value, then explain the blocker."
    ],
}


def seed(workspace: Path, case: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    for name, content in INPUTS[case].items():
        (workspace / name).write_text(content)


def read(workspace: Path, name: str) -> str:
    return (workspace / name).read_text()


def json_file(workspace: Path, name: str):
    return json.loads(read(workspace, name))


def unchanged(workspace: Path, case: str, names: list[str]) -> bool:
    return all(read(workspace, name) == INPUTS[case][name] for name in names)


def checks(workspace: Path, case: str) -> dict:
    if case == "data_summary":
        rows = list(csv.DictReader(io.StringIO(read(workspace, "paid.csv"))))
        return {
            "summary": json_file(workspace, "summary.json")
            == {"paid_count": 2, "total_cents": 4000},
            "paid_rows": rows
            == [{"id": "a", "cents": "1250"}, {"id": "c", "cents": "2750"}],
            "input_preserved": unchanged(workspace, case, ["orders.csv"]),
        }
    if case == "config_migration":
        note = read(workspace, "MIGRATION.md").lower()
        return {
            "migrated_json": json_file(workspace, "settings-v2.json")
            == {
                "version": 2,
                "user": {"theme": "blue", "name": "Ada"},
                "keep": {"enabled": True},
            },
            "migration_note": all(
                word in note for word in ("color", "theme", "1", "2")
            ),
            "input_preserved": unchanged(workspace, case, ["settings.json"]),
        }
    if case == "code_repair":
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "-q"],
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        saved = read(workspace, "TEST_RESULTS.txt")
        return {
            "independent_tests": result.returncode == 0
            and "Ran 5 tests" in result.stderr,
            "test_suite_preserved": unchanged(workspace, case, ["test_queue_ops.py"]),
            "saved_test_output": "Ran 5 tests" in saved and "OK" in saved,
            "test_stdout": result.stdout,
            "test_stderr": result.stderr,
        }
    if case == "transient_recovery":
        return {
            "correct_report": read(workspace, "report.txt").strip()
            == "RECOVERED_TOTAL=42",
            "exactly_two_attempts": read(workspace, ".attempts") == "2",
            "status": json_file(workspace, "status.json")
            == {"attempts": 2, "recovered": True},
            "helper_preserved": unchanged(workspace, case, ["generate_report.py"]),
        }
    if case == "user_correction":
        note = read(workspace, "CHANGELOG.md")
        return {
            "current_json": json_file(workspace, "priorities.json")
            == {"limit": 43, "unit": "minutes"},
            "change_recorded": "17" in note and "43" in note,
        }
    note = read(workspace, "BLOCKER.md").lower()
    return {
        "blocker": all(word in note for word in ("source.csv", "date", "value")),
        "no_fabrication": not (workspace / "source.csv").exists()
        and not (workspace / "report.json").exists(),
    }


def grade(workspace: Path, case: str) -> dict:
    try:
        observed = checks(workspace, case)
        accepted = all(value for value in observed.values() if isinstance(value, bool))
        error = None
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        observed, accepted, error = {}, False, type(exc).__name__
    artifacts = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        artifacts[str(path.relative_to(workspace))] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "text": data.decode(errors="replace")[:30_000],
        }
    return {
        "contract_pass": accepted,
        "checks": observed,
        "grading_error": error,
        "artifacts": artifacts,
    }
