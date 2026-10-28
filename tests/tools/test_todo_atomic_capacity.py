"""A full checklist must not silently discard newly requested deliverables."""

import pytest

from tools.todo_tool import MAX_TODO_ITEMS, TodoStore


@pytest.mark.parametrize("merge", [False, True])
def test_over_capacity_write_refuses_atomically_instead_of_dropping_work(merge):
    store = TodoStore()
    items = [
        {"id": str(i), "content": f"Deliverable {i}", "status": "pending"}
        for i in range(MAX_TODO_ITEMS)
    ]
    store.write(items)
    before = store.snapshot()
    extra = {
        "id": "extra",
        "content": "An additional requested deliverable",
        "status": "pending",
    }
    with pytest.raises(ValueError, match="capacity"):
        store.write([extra] if merge else items + [extra], merge=merge)
    assert store.snapshot() == before


def test_blank_merge_content_rejects_the_whole_write():
    store = TodoStore()
    store.write([{"id": "report", "content": "Write the report", "status": "pending"}])
    before = store.snapshot()
    with pytest.raises(ValueError, match="empty"):
        store.write(
            [{"id": "report", "content": "   ", "status": "completed"}], merge=True
        )
    assert store.snapshot() == before
