"""Record real native stat/fstat observations without exposing host paths."""

import json
import os
from pathlib import Path
import tempfile

from hermes_platform.file_stamps import file_metadata
from tools.file_tools_read_tracking import _file_version


def main():
    observations = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "probe.txt"
        for stage, content in (("created", b"first\n"), ("rewritten", b"other\n")):
            path.write_bytes(content)
            with path.open("rb") as stream:
                by_path = file_metadata(path.stat())
                by_handle = file_metadata(os.fstat(stream.fileno()))
            observations.append({"stage": stage, "path_metadata": by_path, "descriptor_metadata": by_handle,
                                 "cross_api_equal": by_path == by_handle,
                                 "snapshot_available": _file_version(str(path)) is not None})
    print(json.dumps({"native_file_identity": observations}))


if __name__ == "__main__":
    main()
