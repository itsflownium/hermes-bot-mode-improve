"""Line-ending differences must not make a patch choose a similar neighboring line."""

import json

import pytest

from tools.file_tools import clear_file_ops_cache
from tools.fuzzy_match import fuzzy_find_and_replace
from tools.registry import registry


@pytest.mark.parametrize("ending,anchor_ending", [("\r\n", "\n"), ("\n", "\r\n")])
def test_registry_patch_changes_the_exact_line_and_preserves_neighbors(tmp_path, ending, anchor_ending):
    path = tmp_path / "lines.txt"
    path.write_bytes(("line 1" + ending + "line 2" + ending).encode())
    task_id = "line-ending-patch"
    try:
        result = json.loads(registry.dispatch("patch", {
            "path": str(path), "old_string": "line 1" + anchor_ending,
            "new_string": "LINE 1" + anchor_ending,
        }, task_id=task_id))
        assert result.get("success") is True, result
        assert path.read_bytes() == ("LINE 1" + ending + "line 2" + ending).encode()
    finally:
        clear_file_ops_cache(task_id)


def test_line_ending_equivalent_anchors_keep_ambiguity_and_replace_all_contracts():
    content = "alpha\r\nbeta\r\nalpha\r\nbeta\r\n"
    unchanged, count, _, error = fuzzy_find_and_replace(content, "alpha\nbeta\n", "new\n")
    assert unchanged == content and count == 0 and "Found 2 matches" in error
    replaced, count, _, error = fuzzy_find_and_replace(content, "alpha\nbeta\n", "new\n", replace_all=True)
    assert error is None and count == 2
    assert replaced == "new\r\nnew\r\n"
