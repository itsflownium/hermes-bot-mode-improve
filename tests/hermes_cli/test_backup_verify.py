"""Verified full backups reject corrupt output before publication and retention."""

from argparse import ArgumentParser, Namespace
from pathlib import Path
import sqlite3
import zipfile

import pytest

from hermes_cli import backup
from hermes_cli.subcommands.backup import build_backup_parser


def _home(tmp_path, monkeypatch):
    root = tmp_path / "hermes-home"
    root.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (root / "config.yaml").write_text("model: fixture\n")
    return root


def test_verified_backup_reads_all_members_and_preserves_sqlite(
    tmp_path, monkeypatch, capsys
):
    root = _home(tmp_path, monkeypatch)
    with sqlite3.connect(root / "state.db") as db:
        db.execute("CREATE TABLE facts (value TEXT)")
        db.execute("INSERT INTO facts VALUES ('durable fixture')")
    output = tmp_path / "verified.zip"
    assert backup.run_backup(Namespace(output=str(output), verify=True))
    assert "Archive integrity verified" in capsys.readouterr().out
    with zipfile.ZipFile(output) as archive:
        assert backup._find_corrupt_members(archive, archive.namelist()) == []
        restored = tmp_path / "restored.db"
        restored.write_bytes(archive.read("state.db"))
    with sqlite3.connect(restored) as db:
        assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert db.execute("SELECT value FROM facts").fetchall() == [
            ("durable fixture",)
        ]


def test_bad_crc_keeps_previous_archive_and_does_not_prune(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    output = tmp_path / "hermes-backup-current.zip"
    output.write_bytes(b"previous archive")
    older = tmp_path / "hermes-backup-older.zip"
    older.write_bytes(b"older archive")
    write = backup._write_zip_entries

    def corrupt_crc(zf, *args, **kwargs):
        total = write(zf, *args, **kwargs)
        # The directory closes normally, but the stored CRC disagrees with real member data.
        # This reproduces corrupt output without mocking the verifier or its read path.
        zf.filelist[0].CRC ^= 0xFFFFFFFF
        return total

    monkeypatch.setattr(backup, "_write_zip_entries", corrupt_crc)
    with pytest.raises(SystemExit) as failure:
        backup.run_backup(Namespace(output=str(output), verify=True, keep=1))
    assert failure.value.code == 1
    assert output.read_bytes() == b"previous archive"
    assert older.read_bytes() == b"older archive"
    assert not list(tmp_path.glob("*.partial"))


def test_cli_verify_flag_is_consumable_and_cannot_be_ignored_by_quick_mode():
    parser = ArgumentParser()
    build_backup_parser(parser.add_subparsers(), cmd_backup=lambda args: None)
    assert parser.parse_args(["backup", "--verify"]).verify is True
    with pytest.raises(SystemExit):
        parser.parse_args(["backup", "--quick", "--verify"])
