"""CLI verification cannot clear another session's edits made during its run."""

import argparse
import json
import shlex
import sys

import pytest

from agent.verification_evidence import mark_workspace_edited, verification_status
from hermes_cli.verify_cmd import run_verify_command


@pytest.mark.platforms("posix")
def test_cli_run_that_changes_inputs_does_not_bank_a_shared_pass(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_VERIFY_ON_STOP", "1")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    changed = root / "app.py"
    changed.write_text("value = 1\n")
    check = root / "check.py"
    check.write_text("from pathlib import Path\nPath('app.py').write_text('value = 2\\n')\nprint('passed')\n")
    manifest = root / ".hermes"
    manifest.mkdir()
    (manifest / "environment.json").write_text(json.dumps({
        "version": 1, "recipe": {"name": "fixture", "test": [shlex.join([sys.executable, str(check)])]},
    }))
    args = argparse.Namespace(path=str(root), detect_only=False, save=False, skip_start=False,
                              phase=None, port=None, timeout=10, ready_timeout=5, json=True)
    mark_workspace_edited(session_id="editor", cwd=root, paths=[str(changed)])

    assert run_verify_command(args) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    status = verification_status(session_id="editor", cwd=root)
    assert status["status"] == "stale"
    assert status["changed_paths"] == [str(changed)]
    assert status["evidence"]["snapshot"]["binding"] == "execution"

    # A second run against unchanged content is reusable, even if the script rewrites
    # the same bytes and the CLI records under a different session.
    assert run_verify_command(args) == 0
    assert verification_status(session_id="editor", cwd=root)["status"] == "passed"
