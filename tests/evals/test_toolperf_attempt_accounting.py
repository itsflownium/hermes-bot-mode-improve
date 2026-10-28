"""The live A/B harness must account for every launch and emit usable Relay configuration."""

import json
import subprocess

import pytest

from evals.toolperf_abeval import ab_eval


def test_failed_attempt_is_retained_when_resuming_a_logical_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ab_eval, "ROOT", tmp_path)
    monkeypatch.setattr(ab_eval, "HOME", tmp_path / "home")
    task = next(iter(ab_eval.TASKS))
    result_dir = tmp_path / "results" / "test_model" / "baseline"
    attempts_path = result_dir / "attempts.jsonl"
    launches = []
    starts_visible = []

    def invoke(command, **_kwargs):
        launches.append(command)
        starts_visible.append(attempts_path.exists())
        if len(launches) == 1:
            raise subprocess.TimeoutExpired(command, timeout=600)
        return subprocess.CompletedProcess(command, 0, stdout="completed", stderr="")

    monkeypatch.setattr(ab_eval.subprocess, "run", invoke)
    ab_eval.run("baseline", "test/model", 1, str(tmp_path), only=[task])
    assert attempts_path.exists(), "a timed-out launch must remain in the attempt denominator"
    with attempts_path.open("a") as output:
        output.write('{"interrupted_record":')
    ab_eval.run("baseline", "test/model", 1, str(tmp_path), only=[task])
    ab_eval.run("baseline", "test/model", 1, str(tmp_path), only=[task])

    events = []
    for line in attempts_path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    assert [event["state"] for event in events] == ["started", "timeout", "started", "completed"]
    assert events[0]["attempt_id"] == events[1]["attempt_id"]
    assert events[2]["attempt_id"] == events[3]["attempt_id"] != events[0]["attempt_id"]
    assert len(launches) == 2 and all(starts_visible)
    assert len((result_dir / "meta.jsonl").read_text().splitlines()) == 1

    ab_eval.report(["test/model"])
    output = capsys.readouterr().out
    assert "launched=2" in output and "timeout=1" in output and "completed=1" in output
    assert "invalid_records=1" in output


def test_generated_configuration_is_accepted_by_the_installed_relay(tmp_path, monkeypatch):
    relay = pytest.importorskip("nemo_relay")
    if getattr(relay, "_native", None) is None:
        pytest.skip("native Relay is unavailable on this platform")
    monkeypatch.setattr(ab_eval, "ROOT", tmp_path)
    monkeypatch.setattr(ab_eval, "HOME", tmp_path / "home")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    task = next(iter(ab_eval.TASKS))
    validations = []

    def invoke(command, **kwargs):
        selected = kwargs["env"]["HERMES_NEMO_RELAY_PLUGINS_TOML"]
        report = relay.plugin.validate({}, additional_plugins_toml=selected)
        diagnostics = (report.get("config") or {}).get("diagnostics") or []
        validations.extend(item for item in diagnostics if item.get("level") == "error")
        return subprocess.CompletedProcess(command, 0, stdout="completed", stderr="")

    monkeypatch.setattr(ab_eval.subprocess, "run", invoke)
    ab_eval.run("baseline", "test/model", 1, str(tmp_path), only=[task])
    assert not validations, validations


@pytest.mark.parametrize("outcome,state", [
    ("spawn_failure", "infra_failure"), ("empty_failure", "infra_failure"),
    ("partial_failure", "agent_failure"), ("interrupted", "incomplete"),
])
def test_attempt_report_keeps_launch_failures_and_interrupted_receipts(
    tmp_path, monkeypatch, capsys, outcome, state,
):
    monkeypatch.setattr(ab_eval, "ROOT", tmp_path)
    monkeypatch.setattr(ab_eval, "HOME", tmp_path / "home")
    task = next(iter(ab_eval.TASKS))

    def invoke(command, **_kwargs):
        if outcome == "spawn_failure":
            raise OSError("synthetic launch refusal")
        if outcome == "interrupted":
            raise KeyboardInterrupt
        stdout = "partial result" if outcome == "partial_failure" else ""
        return subprocess.CompletedProcess(command, 1, stdout=stdout, stderr="")

    monkeypatch.setattr(ab_eval.subprocess, "run", invoke)
    if outcome == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            ab_eval.run("baseline", "test/model", 1, str(tmp_path), only=[task])
    else:
        ab_eval.run("baseline", "test/model", 1, str(tmp_path), only=[task])
    attempts_path = tmp_path / "results" / "test_model" / "baseline" / "attempts.jsonl"
    with attempts_path.open("a") as output:
        output.write('{"attempt_id":')
    ab_eval.report(["test/model"])
    output = capsys.readouterr().out
    assert "launched=1" in output and f"{state}=1" in output and "invalid_records=1" in output

