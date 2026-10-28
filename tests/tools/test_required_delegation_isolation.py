"""Required isolation refuses an unisolated start and verifies the real initial cwd."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import delegate_tool, terminal_tool
from tools.delegate_tool_child_run import _ChildRun, _create_isolated_worktree


def _required_config():
    from hermes_cli.config import set_config_value

    set_config_value("delegation.worktree_isolation", "required")


def _repository(tmp_path):
    path = tmp_path / "repository"
    path.mkdir()

    def git(*args):
        subprocess.run(
            ["git", "-C", str(path), "-c", "core.hooksPath=", *args],
            capture_output=True,
            check=True,
            timeout=10,
        )

    git("init", "-q")
    (path / "artifact.txt").write_text("base\n")
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
    return path


def test_required_config_refuses_non_git_and_nonlocal_workspaces(tmp_path, monkeypatch):
    _required_config()
    monkeypatch.setattr(terminal_tool, "get_session_cwd", lambda _key: str(tmp_path))
    with pytest.raises(RuntimeError, match="committed local Git"):
        _create_isolated_worktree(SimpleNamespace(), "owner", "no-repo")
    monkeypatch.setattr("tools.subagent_worktree.local_backend_active", lambda: False)
    with pytest.raises(RuntimeError, match="terminal backend"):
        _create_isolated_worktree(SimpleNamespace(), "owner", "nonlocal")
    monkeypatch.setattr(delegate_tool, "_get_worktree_isolation", lambda: True)
    assert _create_isolated_worktree(SimpleNamespace(), "owner", "best-effort") is None


@pytest.mark.parametrize("binding_fails", [False, True])
def test_required_worktree_seed_verifies_cwd_or_refuses(
    tmp_path, monkeypatch, binding_fails
):
    _required_config()
    repository = _repository(tmp_path)
    parent_id = "required-owner"
    terminal_tool.record_session_cwd(parent_id, str(repository))
    child = SimpleNamespace(_delegate_profile_home=None, _delegate_output_schema=None)
    run = _ChildRun(
        child,
        SimpleNamespace(_current_task_id=parent_id),
        0,
        "Edit artifact",
        "isolated-child",
        None,
    )
    if binding_fails:
        record = terminal_tool.record_session_cwd

        def fail_worktree_binding(key, cwd):
            if cwd and ".worktrees" in Path(cwd).parts:
                raise OSError("fixture binding failure")
            return record(key, cwd)

        monkeypatch.setattr(terminal_tool, "record_session_cwd", fail_worktree_binding)
        with pytest.raises(RuntimeError, match="cwd binding failed"):
            run.seed_workspace()
    else:
        run.seed_workspace()
        assert (
            Path(terminal_tool.get_session_cwd(run.child_task_id)).resolve()
            == Path(run.worktree_info["path"]).resolve()
        )
        assert Path(run.worktree_info["path"], "artifact.txt").read_text() == "base\n"
        assert "WORKTREE ISOLATION" in run.goal
    result = run.attach_worktree({"status": "failed" if binding_fails else "completed"})
    assert result["worktree"]["isolation_required"] is True
    assert result["worktree"]["cwd_verified"] is not binding_fails
    assert result["worktree"]["base_commit"] == run.worktree_info["base_commit"]
    assert (repository / "artifact.txt").read_text() == "base\n"


def test_worktree_uses_its_recorded_base_when_parent_head_changes(
    tmp_path, monkeypatch
):
    from tools import subagent_worktree

    repository = _repository(tmp_path)
    run_git = subagent_worktree._run_git
    raced = False

    def race_before_checkout(args, cwd, **kwargs):
        nonlocal raced
        if args[:2] == ["worktree", "add"] and not raced:
            raced = True
            (repository / "artifact.txt").write_text("new parent head\n")
            run_git(["add", "artifact.txt"], str(repository))
            committed = run_git(
                [
                    "-c",
                    "user.name=fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-qm",
                    "concurrent fixture",
                ],
                str(repository),
            )
            assert committed.returncode == 0
        return run_git(args, cwd, **kwargs)

    monkeypatch.setattr(subagent_worktree, "_run_git", race_before_checkout)
    info = subagent_worktree.create_subagent_worktree(str(repository), "pinned-base")
    assert info is not None and raced
    actual = run_git(["rev-parse", "HEAD"], info["path"]).stdout.strip()
    assert actual == info["base_commit"]
    assert Path(info["path"], "artifact.txt").read_text() == "base\n"
    assert (repository / "artifact.txt").read_text() == "new parent head\n"
    subagent_worktree.finalize_subagent_worktree(info)


def test_required_isolation_failure_never_starts_the_child_model(tmp_path, monkeypatch):
    _required_config()
    monkeypatch.setattr(terminal_tool, "get_session_cwd", lambda _key: str(tmp_path))
    started = []
    child = SimpleNamespace(
        session_id="required-refused-child",
        _subagent_id=None,
        _delegate_saved_tool_names=[],
        _credential_pool=None,
        tool_progress_callback=None,
        quiet_mode=True,
        model="fixture",
        _delegate_output_schema=None,
    )
    child.run_conversation = lambda **kwargs: (
        started.append(kwargs) or {"completed": True, "final_response": "unexpected"}
    )
    child.close = lambda: None
    result = delegate_tool._run_single_child(
        0, "Edit safely", child, SimpleNamespace(_current_task_id="owner")
    )
    assert result["status"] == "error" and "Required worktree" in result["error"]
    assert started == []
