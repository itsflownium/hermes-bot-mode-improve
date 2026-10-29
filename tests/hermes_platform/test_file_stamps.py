"""Timestamp-origin differences are allowed; same-origin changes and replacements are not."""

from types import SimpleNamespace

from hermes_platform.file_stamps import stable_open_file


def _stat(ctime=40, **changes):
    return SimpleNamespace(**({"st_dev": 10, "st_ino": 20, "st_size": 5, "st_mtime_ns": 30, "st_ctime_ns": ctime, "st_mode": 0o100644} | changes))


def test_distinct_timestamp_origins_preserve_identity_without_weakening_change_detection():
    assert stable_open_file(_stat(), _stat(ctime=1), _stat(ctime=1), _stat())
    assert not stable_open_file(_stat(), _stat(ctime=1), _stat(ctime=2), _stat())
    assert not stable_open_file(_stat(), _stat(ctime=1), _stat(ctime=1), _stat(ctime=41))
    assert not stable_open_file(_stat(), _stat(st_ino=99), _stat(st_ino=99), _stat())
    assert not stable_open_file(_stat(), _stat(st_mtime_ns=31), _stat(st_mtime_ns=31), _stat())
    assert not stable_open_file(_stat(), _stat(), _stat(), _stat(st_mode=0o100755))
