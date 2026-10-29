"""File identity checks without conflating path and descriptor timestamp semantics."""

import os


def file_metadata(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def stable_open_file(path_before, opened, closed, path_after) -> bool:
    """Both observations must stay stable and refer to the same file and bytes.

    Windows path stat and descriptor stat can expose different ctime values.
    Compare ctime within each API, never between APIs. Device/inode, size and
    last-write time must still agree across the open descriptor and its path.
    """
    expected, descriptor = file_metadata(path_before), file_metadata(opened)
    return (expected == file_metadata(path_after)
            and descriptor == file_metadata(closed)
            and expected[:4] == descriptor[:4]
            and path_before.st_mode == path_after.st_mode
            and opened.st_mode == closed.st_mode)
