"""Optional archive integrity checks before a full backup is published or rotated."""

from __future__ import annotations

import logging
import zipfile
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


def verify_archive(path: Path) -> None:
    from hermes_cli import backup

    logger.info("backup phase=verify status=started")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            bad = backup._find_corrupt_members(archive, archive.namelist())
    except (OSError, *backup._ZIP_MEMBER_READ_ERRORS) as exc:
        bad = [f"archive could not be read ({type(exc).__name__})"]
    if bad:
        logger.error("backup phase=verify status=failed errors=%d", len(bad))
        print(
            "Error: backup archive integrity verification failed; the new archive was not published."
        )
        backup._print_capped("  Verification errors:", bad, "  ")
        raise SystemExit(1)
    logger.info("backup phase=verify status=complete")
    print("Archive integrity verified (decompression and CRC; restore not exercised).")


@contextmanager
def archive_output(out_path: Path, *, verify: bool = False):
    from hermes_cli.backup import _atomic_output_path

    with _atomic_output_path(out_path) as partial:
        with zipfile.ZipFile(
            partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            yield archive
        if verify:
            verify_archive(partial)
