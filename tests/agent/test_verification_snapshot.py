"""Verification proves the selected inputs at the time of the check."""

import os
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from agent.verification_evidence import (
    mark_workspace_edited,
    record_terminal_result,
    verification_status,
)
from agent.verification_stop import build_verify_on_stop_nudge


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VERIFY_ON_STOP", "1")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "alpha.py").write_text("value = 1\n")
    (root / "src" / "beta.py").write_text("value = 2\n")
    (root / "tests" / "test_alpha.py").write_text("def test_alpha(): pass\n")
    return root


def test_targeted_check_does_not_verify_unrelated_edit(project):
    changed = str(project / "src" / "beta.py")
    mark_workspace_edited(session_id="s1", cwd=project, paths=[changed])
    record_terminal_result(
        command="pytest tests/test_alpha.py", cwd=project, session_id="s1", exit_code=0,
    )

    status = verification_status(session_id="s1", cwd=project)
    assert status["evidence"]["status"] == "passed"
    assert status["status"] != "passed"
    assert changed in status["changed_paths"]
    assert build_verify_on_stop_nudge(session_id="s1", changed_paths=[changed]) is not None


def test_pass_is_stale_after_unreported_content_change(project):
    record_terminal_result(command="pytest", cwd=project, session_id="s1", exit_code=0)
    assert verification_status(session_id="s1", cwd=project)["status"] == "passed"
    changed = project / "src" / "beta.py"
    before = changed.stat()
    changed.write_text("value = 3\n")
    os.utime(changed, ns=(before.st_atime_ns, before.st_mtime_ns))

    assert verification_status(session_id="s1", cwd=project)["status"] == "stale"
    assert build_verify_on_stop_nudge(session_id="s1", changed_paths=[str(changed)]) is not None


def test_explicit_target_covers_only_the_edited_file(project):
    changed = str(project / "tests" / "test_alpha.py")
    mark_workspace_edited(session_id="s1", cwd=project, paths=[changed])
    record_terminal_result(command="pytest tests/test_alpha.py", cwd=project, session_id="s1", exit_code=0)
    assert build_verify_on_stop_nudge(session_id="s1", changed_paths=[changed]) is None

    other = str(project / "src" / "beta.py")
    assert build_verify_on_stop_nudge(session_id="s1", changed_paths=[other]) is not None
    record_terminal_result(command="pytest", cwd=project, session_id="s1", exit_code=0)
    assert build_verify_on_stop_nudge(session_id="s1", changed_paths=[changed, other]) is None


@pytest.mark.parametrize("command", [
    "pytest -k alpha", "pytest tests/test_alpha.py::test_other", "pytest --co",
    "pytest --collectonly", "pytest --setup-only", "pytest --version", "pytest --help",
    "scripts/run_tests.sh --slice=0/4", "PYTEST_ADDOPTS=--collect-only pytest",
    "env PYTEST_ADDOPTS=-kalpha pytest",
])
def test_name_selection_does_not_claim_full_file_coverage(project, command):
    if command.startswith("scripts/"):
        (project / "scripts").mkdir()
        (project / "scripts" / "run_tests.sh").write_text("#!/bin/sh\n")
    changed = str(project / "tests" / "test_alpha.py")
    mark_workspace_edited(session_id="s1", cwd=project, paths=[changed])
    event = record_terminal_result(command=command, cwd=project, session_id="s1", exit_code=0)
    assert event["scope"] == "targeted"
    assert build_verify_on_stop_nudge(session_id="s1", changed_paths=[changed]) is not None


def test_shared_workspace_pass_requires_matching_content(project):
    from agent.verification_evidence import record_verify_run

    mark_workspace_edited(session_id="editor", cwd=project, paths=[str(project / "src" / "beta.py")])
    record_verify_run(root=project, session_id="verifier", ok=True)
    assert verification_status(session_id="editor", cwd=project)["status"] == "passed"
    (project / "src" / "beta.py").unlink()
    assert verification_status(session_id="editor", cwd=project)["status"] == "stale"


def test_legacy_ledger_keeps_its_edits_but_requires_content_proof(project, monkeypatch, tmp_path):
    home = tmp_path / "legacy-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    changed = str(project / "src" / "beta.py")
    with sqlite3.connect(home / "verification_evidence.db") as conn:
        conn.executescript("""
            CREATE TABLE verification_events (
                id INTEGER PRIMARY KEY, created_at TEXT, session_id TEXT, cwd TEXT, root TEXT,
                command TEXT, canonical_command TEXT, kind TEXT, scope TEXT, status TEXT,
                exit_code INTEGER, output_summary TEXT
            );
            CREATE TABLE verification_state (
                session_id TEXT, root TEXT, last_event_id INTEGER, last_edit_at TEXT,
                changed_paths_json TEXT, PRIMARY KEY(session_id, root)
            );
        """)
        conn.execute("INSERT INTO verification_events VALUES (1, ?, 's1', ?, ?, 'pytest', 'pytest', 'test', 'full', 'passed', 0, 'green')",
                     ("2026-10-01T12:00:00+00:00", str(project), str(project)))
        conn.execute("INSERT INTO verification_state VALUES ('s1', ?, 1, NULL, ?)",
                     (str(project), json.dumps([changed])))

    status = verification_status(session_id="s1", cwd=project)
    assert status["status"] == "stale"
    assert status["evidence"]["id"] == 1
    assert status["changed_paths"] == [changed]
    record_terminal_result(command="pytest", cwd=project, session_id="s1", exit_code=0)
    assert verification_status(session_id="s1", cwd=project)["status"] == "passed"


def test_git_worktree_snapshots_preserve_deletions_and_ignore_generated_files(project, tmp_path):
    def git(root: Path, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)

    (project / ".gitignore").write_text("generated.cache\n")
    git(project, "init", "-q")
    git(project, "add", ".")
    git(project, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    worktree = tmp_path / "worktree"
    git(project, "worktree", "add", "--detach", str(worktree), "HEAD")
    changed = worktree / "src" / "beta.py"
    changed.unlink()
    record_terminal_result(command="pytest", cwd=worktree, session_id="s1", exit_code=0)
    (worktree / "generated.cache").write_text("test output")
    assert verification_status(session_id="s1", cwd=worktree)["status"] == "passed"
    record_terminal_result(command="pytest", cwd=worktree, session_id="s1", exit_code=0)
    assert verification_status(session_id="s1", cwd=worktree)["status"] == "passed"
    changed.write_text("value = 2\n")
    assert verification_status(session_id="s1", cwd=worktree)["status"] == "stale"


def test_incomplete_snapshot_does_not_verify_the_workspace(project, monkeypatch):
    from agent import verification_snapshot

    monkeypatch.setattr(verification_snapshot, "_MAX_FILES", 0)
    record_terminal_result(command="pytest", cwd=project, session_id="s1", exit_code=0)
    status = verification_status(session_id="s1", cwd=project)
    assert status["status"] == "unverified"
    assert "limit" in status["reason"]


def test_disabled_guard_does_not_scan_inputs_or_create_a_ledger(project, monkeypatch, tmp_path):
    from agent import verification_snapshot
    from agent.verification_evidence import begin_verification

    monkeypatch.setenv("HERMES_VERIFY_ON_STOP", "0")

    def unexpected_scan(*args, **kwargs):
        raise AssertionError("disabled verification must not scan workspace inputs")

    monkeypatch.setattr(verification_snapshot, "capture_workspace_snapshot", unexpected_scan)
    assert begin_verification(command="pytest", cwd=project) is None
    assert record_terminal_result(command="pytest", cwd=project, session_id="s1", exit_code=0) is None
    assert not (tmp_path / "home" / "verification_evidence.db").exists()


def test_completion_receipt_reuses_its_snapshot_but_later_status_rechecks(project, monkeypatch):
    from agent import verification_snapshot
    from agent.verification_evidence import _recorded_verification_status, begin_verification

    event = record_terminal_result(command="pytest", cwd=project, session_id="s1", exit_code=0,
                                   snapshot=begin_verification(command="pytest", cwd=project))

    def unexpected_scan(*args, **kwargs):
        raise AssertionError("the receipt already has its completed content snapshot")

    with monkeypatch.context() as scoped:
        scoped.setattr(verification_snapshot, "capture_workspace_snapshot", unexpected_scan)
        assert _recorded_verification_status(event)["status"] == "passed"
    (project / "src" / "beta.py").write_text("value = 3\n")
    assert verification_status(session_id="s1", cwd=project)["status"] == "stale"


@pytest.mark.platforms("posix")
def test_external_symlink_is_unbound_instead_of_hashing_another_workspace(project, tmp_path):
    from agent.verification_snapshot import capture_workspace_snapshot

    outside = tmp_path / "outside.py"
    outside.write_text("value = 4\n")
    (project / "linked.py").symlink_to(outside)
    assert capture_workspace_snapshot(project)["fingerprint"] is None
