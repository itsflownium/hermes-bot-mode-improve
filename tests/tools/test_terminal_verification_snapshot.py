"""The real terminal dispatch binds proof before a foreground process executes."""

import importlib
import json
import shlex
import subprocess
import sys

import pytest

from agent.verification_evidence import mark_workspace_edited, verification_status
from tools.registry import registry


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("backend, mutate, expected", [
    ("local", False, "passed"), ("local", True, "stale"), ("ssh", False, "unverified"),
])
def test_foreground_receipt_verifies_only_the_content_that_ran(tmp_path, monkeypatch, backend, mutate, expected):
    terminal = importlib.import_module("tools.terminal_tool")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HERMES_VERIFY_ON_STOP", "1")
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    target = root / "app.py"
    target.write_text("value = 1\n")
    check = root / "check.py"
    check.write_text(
        "from pathlib import Path\n"
        + ("Path('app.py').write_text('value = 2\\n')\n" if mutate else "")
        + "print('check passed')\n"
    )
    scripts = root / "scripts"
    scripts.mkdir()
    runner = scripts / "run_tests.sh"
    runner.write_text("#!/bin/sh\n" + shlex.join([sys.executable, str(check)]) + "\n")
    runner.chmod(0o755)

    class Environment:
        cwd = str(root)

        def execute(self, command, **kwargs):
            result = subprocess.run(["sh", "-c", command], cwd=kwargs["cwd"],
                                    timeout=kwargs["timeout"], capture_output=True, text=True, check=False)
            return {"returncode": result.returncode, "output": result.stdout + result.stderr}

    plan = terminal._ExecPlan(config={}, env_type=backend, effective_task_id="verification-test",
                              image="", cwd=str(root), host_cwd=None, effective_timeout=10)
    monkeypatch.setattr(terminal, "_plan_execution", lambda *args, **kwargs: plan)
    monkeypatch.setattr(terminal, "_acquire_env", lambda *args, **kwargs: Environment())
    monkeypatch.setattr(terminal, "_pre_exec_block", lambda *args, **kwargs: None)
    monkeypatch.setattr(terminal, "_run_approval_guards", lambda *args, **kwargs: terminal._ApprovalVerdict())
    monkeypatch.setattr(terminal, "_yield_kwargs", lambda *args, **kwargs: {})
    mark_workspace_edited(session_id="s1", cwd=root, paths=[str(target)])

    result = json.loads(registry.dispatch("terminal", {"command": "scripts/run_tests.sh", "workdir": str(root)},
                                          task_id="verification-test", session_id="s1"))
    assert result["exit_code"] == 0
    assert result["verification_evidence"]["check_status"] == "passed"
    assert result["verification_evidence"]["status"] == expected
    assert verification_status(session_id="s1", cwd=root)["status"] == expected
    if backend == "local":
        assert result["verification_evidence"]["snapshot"]["binding"] == "execution"
