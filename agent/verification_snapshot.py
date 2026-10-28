"""Bounded content fingerprints for local verification inputs.

Only digests leave this module. A partial or unreadable scan never becomes proof.
Git supplies the input set when available; caches and installed/build outputs are
excluded from an unversioned workspace's fallback walk.
"""

from __future__ import annotations

import hashlib
import os
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


_MAX_FILES = 50_000
_MAX_BYTES = 256 * 1024 * 1024
_MAX_SECONDS = 5.0
_DIGEST_WORKERS = 8
_DIGEST_BATCH_SIZE = 128
_GENERATED_DIRS = frozenset({
    ".git", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".cache", "dist", "build", "target", ".next", ".turbo",
})
_GENERATED_FILES = frozenset({".coverage", "coverage.xml"})


def _git_paths(root: Path) -> list[str]:
    from hermes_cli._subprocess_compat import bounded_probe_run, noninteractive_git_env

    result = bounded_probe_run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        timeout=2.5, env=noninteractive_git_env(),
    )
    if result is None or result.returncode != 0:
        raise OSError("Git input enumeration failed")
    return sorted(set(filter(None, (result.stdout or "").split("\0"))))


def _walk_paths(root: Path, home: Path) -> list[str]:
    paths: list[str] = []

    def failed(error: OSError) -> None:
        raise error

    for directory, dirs, files in os.walk(root, onerror=failed):
        dirs[:] = sorted(d for d in dirs if d not in _GENERATED_DIRS and not (Path(directory) / d).is_relative_to(home))
        for name in files:
            if name not in _GENERATED_FILES and not name.endswith((".pyc", ".pyo")):
                paths.append((Path(directory) / name).relative_to(root).as_posix())
        # os.walk does not follow symlinked directories; do not silently omit them.
        paths.extend((Path(directory) / d).relative_to(root).as_posix() for d in dirs
                     if (Path(directory) / d).is_symlink())
        if len(paths) > _MAX_FILES:
            raise OSError("workspace exceeds the verification input limit")
    return sorted(paths)


def _input_paths(root: Path, home: Path) -> list[str]:
    paths = _git_paths(root) if (root / ".git").exists() else _walk_paths(root, home)
    if not home.is_relative_to(root):
        return paths
    prefix = home.relative_to(root).as_posix()
    return [p for p in paths if p != prefix and not p.startswith(prefix + "/")]


def _stamp(info: os.stat_result) -> tuple[int, ...]:
    return info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode


def _file_digest(
    path: Path, before: os.stat_result, *, root: Path, remaining: int, deadline: float,
) -> tuple[str, int, tuple[int, ...]]:
    digest = hashlib.sha256()
    digest.update(str(stat.S_IMODE(before.st_mode) & 0o111).encode())
    is_link = stat.S_ISLNK(before.st_mode)
    content_before = before
    if is_link:
        target = path.resolve(strict=True)
        if not target.is_relative_to(root):
            raise OSError("verification input has an external or directory symlink")
        content_before = target.stat()
        digest.update(os.fsencode(os.readlink(path)))
        digest.update(str(stat.S_IMODE(content_before.st_mode) & 0o111).encode())
    if not stat.S_ISREG(content_before.st_mode):
        raise OSError("verification input is not a regular file")
    size = content_before.st_size
    if size > remaining:
        raise OSError("workspace exceeds the verification byte limit")
    if time.monotonic() > deadline:
        raise OSError("workspace exceeds the verification scan time limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    if not is_link:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb", buffering=0) as source:
        if _stamp(os.fstat(source.fileno())) != _stamp(content_before):
            raise OSError("verification input changed before it was opened")
        unread = size
        while unread:
            chunk = source.read(min(1024 * 1024, unread))
            if time.monotonic() > deadline:
                raise OSError("workspace exceeds the verification scan time limit")
            if not chunk:
                raise OSError("verification input changed while it was being read")
            digest.update(chunk)
            unread -= len(chunk)
        content_after = os.fstat(source.fileno())
    if _stamp(content_after) != _stamp(content_before):
        raise OSError("verification input changed while it was being read")
    stamp = _stamp(before) + _stamp(content_before) if is_link else _stamp(before)
    return digest.hexdigest(), size, stamp


def _plan_inputs(root: Path, paths: list[str], *, deadline: float) -> list[tuple]:
    entries = []
    remaining = _MAX_BYTES
    for name in paths:
        if time.monotonic() > deadline:
            raise OSError("workspace exceeds the verification scan time limit")
        path = root / name
        try:
            before = path.lstat()
        except FileNotFoundError:
            entries.append((name, path, None, 0))
            continue
        size = path.stat().st_size if stat.S_ISLNK(before.st_mode) else before.st_size
        remaining -= size
        if remaining < 0:
            raise OSError("workspace exceeds the verification byte limit")
        entries.append((name, path, before, size))
    return entries


def _digest_input(entry: tuple, *, root: Path, deadline: float) -> tuple[str, Path, str, tuple[int, ...] | None]:
    name, path, before, size = entry
    if before is None:
        return name, path, "deleted", None
    value, _, stamp = _file_digest(path, before, root=root, remaining=size, deadline=deadline)
    return name, path, value, stamp


def _hash_inputs(root: Path, entries: list[tuple], *, deadline: float) -> tuple[str, dict]:
    digest = hashlib.sha256(b"hermes-verification-inputs-v1\0")
    stamps = {}
    worker = partial(_digest_input, root=root, deadline=deadline)
    # Bounded batches avoid one Future per file. Workers receive explicit paths and
    # budgets only; no profile state or context-dependent services run in these threads.
    with ThreadPoolExecutor(max_workers=_DIGEST_WORKERS, thread_name_prefix="verification-inputs") as pool:
        for start in range(0, len(entries), _DIGEST_BATCH_SIZE):
            for name, path, value, stamp in pool.map(worker, entries[start:start + _DIGEST_BATCH_SIZE]):
                digest.update(os.fsencode(name) + b"\0" + value.encode() + b"\0")
                stamps[path] = stamp
    return digest.hexdigest(), stamps


def capture_workspace_snapshot(root: str | Path) -> dict[str, Any]:
    """Fingerprint local inputs, or explain why a complete fingerprint is unavailable.

    No mtime cache: same-size writes with restored timestamps must still invalidate proof.
    The budget bounds cost; exceeding it leaves verification explicitly unbound.
    """
    root_path = Path(root).resolve()
    result: dict[str, Any] = {"root": str(root_path), "fingerprint": None}
    started = time.monotonic()
    try:
        home = get_hermes_home().resolve()
        if root_path.is_relative_to(home):
            raise OSError("the workspace is inside the agent runtime home")
        paths = _input_paths(root_path, home)
        if len(paths) > _MAX_FILES:
            raise OSError("workspace exceeds the verification input limit")
        entries = _plan_inputs(root_path, paths, deadline=started + _MAX_SECONDS)
        fingerprint, stamps = _hash_inputs(root_path, entries, deadline=started + _MAX_SECONDS)
        if paths != _input_paths(root_path, home) or any(_current_stamp(path) != stamp for path, stamp in stamps.items()):
            raise OSError("workspace changed during the verification scan")
        result.update(fingerprint=fingerprint, files=len(paths))
    except (OSError, ValueError, RuntimeError) as error:
        # Do not persist exception text: filenames and OS diagnostics may contain secrets.
        result["reason"] = str(error) if type(error) is OSError and not error.filename else "workspace inputs could not be read"
    return result


def _current_stamp(path: Path) -> tuple[int, ...] | None:
    try:
        info = path.lstat()
        return _stamp(info) + _stamp(path.stat()) if stat.S_ISLNK(info.st_mode) else _stamp(info)
    except FileNotFoundError:
        return None


def normalize_paths(paths, *, root: str | Path, cwd: str | Path | None = None) -> list[str]:
    """Workspace-relative paths; outside paths cannot claim coverage inside this root."""
    base = Path(root).resolve()
    normalized: set[str] = set()
    for raw in paths:
        try:
            path = Path(str(raw).split("::", 1)[0]).expanduser()
            path = (path if path.is_absolute() else Path(cwd or base) / path).resolve()
            normalized.add(path.relative_to(base).as_posix())
        except (OSError, ValueError, RuntimeError):
            continue
    return sorted(normalized)


def paths_covered(paths: list[str], targets: list[str]) -> bool:
    """Coverage requires an explicit path or ancestor, never a guessed test/source mapping."""
    return bool(paths) and all(
        any(target == "." or path == target or path.startswith(target.rstrip("/") + "/") for target in targets)
        for path in paths
    )
