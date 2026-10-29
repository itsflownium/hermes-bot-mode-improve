"""Native Windows path aliases must preserve same-file read/write evidence."""

import json
from unittest.mock import patch

import pytest

from tools.file_tools import read_file_tool
from tools.file_tools_read_tracking import _has_full_write_baseline, _read_tracker
from tests.tools.test_file_read_guards import _make_fake_ops


def test_snapshot_remains_available_after_rewrite_with_restored_mtime(tmp_path):
    import os
    from tools.file_tools_read_tracking import _file_metadata, _file_version

    path = tmp_path / "rewritten.txt"
    path.write_bytes(b"first\n")
    before = _file_version(str(path))
    assert before is not None
    info = path.stat()
    path.write_bytes(b"other\n")
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
    after = _file_version(str(path))
    assert after is not None
    assert after[:-1] == _file_metadata(str(path))
    assert before[-1] != after[-1]


@pytest.mark.platforms("windows")
def test_drive_letter_alias_reuses_the_same_file_read(tmp_path):
    path = tmp_path / "read-me.txt"
    content = "same file\n"
    path.write_bytes(content.encode())
    original = str(path)
    alias = original[0].swapcase() + original[1:]
    assert path.drive and original != alias
    _read_tracker.clear()
    with patch("tools.file_tools._get_file_ops", return_value=_make_fake_ops(content=content, file_size=len(content))):
        first = json.loads(read_file_tool(original, task_id="drive-alias"))
        second = json.loads(read_file_tool(alias, task_id="drive-alias"))
    assert first.get("content"), first
    assert second.get("dedup") is True, second


@pytest.mark.platforms("windows")
def test_junction_alias_retains_current_full_read_baseline(tmp_path):
    from pathlib import Path
    import subprocess
    from tools.file_tools_paths import _resolve_path_for_task

    target = tmp_path / "real-directory"
    target.mkdir()
    junction = tmp_path / "alias-directory"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)], check=True, capture_output=True)
    try:
        path = target / "read-me.txt"
        content = "same file\n"
        path.write_bytes(content.encode())
        alias = junction / path.name
        assert alias.read_bytes() == path.read_bytes()
        _read_tracker.clear()
        with patch("tools.file_tools._get_file_ops", return_value=_make_fake_ops(content=content, file_size=len(content))):
            first = json.loads(read_file_tool(str(alias), task_id="junction-alias"))
        assert first.get("content"), first
        resolved = _resolve_path_for_task(str(path), "junction-alias")
        assert _has_full_write_baseline(str(resolved), "junction-alias")
        assert Path(resolved).read_bytes() == content.encode()
    finally:
        junction.rmdir()
