"""Shared reservations preserve local caps, refunds and turn ownership."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.task_budget import (
    inherit_task_budget,
    reset_iteration_budget,
    task_budget_result_fields,
)
from hermes_cli.config import set_config_value


def test_shared_limit_is_atomic_and_refunds_only_owned_iterations():
    set_config_value("delegation.shared_iteration_limit", "17")
    parent = SimpleNamespace(max_iterations=100)
    parent.iteration_budget = reset_iteration_budget(parent)
    children = [SimpleNamespace(max_iterations=5) for _ in range(10)]
    for child in children:
        inherit_task_budget(child, parent)
        child.iteration_budget = reset_iteration_budget(child)

    def reserve(child):
        return sum(child.iteration_budget.consume() for _ in range(10))

    with ThreadPoolExecutor(max_workers=10) as executor:
        counts = list(executor.map(reserve, children))
    assert sum(counts) == 17
    assert max(counts) <= 5
    assert parent.iteration_budget.consume() is False
    # A parent that spent nothing cannot refund another worker's reservation.
    parent.iteration_budget.refund()
    assert parent._task_iteration_pool.used == 17
    funded = next(child for child in children if child.iteration_budget.used)
    funded.iteration_budget.refund()
    assert parent.iteration_budget.consume() is True
    assert (
        task_budget_result_fields(parent)["task_iteration_budget"][
            "physical_request_cap"
        ]
        is False
    )


def test_real_child_factory_captures_pool_and_next_root_turn_gets_a_new_one():
    from tests.tools.test_delegate import _make_mock_parent
    from tools.delegate_tool import _build_child_agent

    set_config_value("delegation.shared_iteration_limit", "2")
    parent = _make_mock_parent()
    parent.max_iterations = 20
    parent.iteration_budget = reset_iteration_budget(parent)
    original = parent._task_iteration_pool
    with patch("run_agent.AIAgent", return_value=MagicMock(max_iterations=3)):
        child = _build_child_agent(
            task_index=0,
            goal="Fixture",
            context=None,
            toolsets=None,
            model=None,
            max_iterations=3,
            parent_agent=parent,
            task_count=1,
            role="leaf",
        )
    child.iteration_budget = reset_iteration_budget(child)
    assert child._task_iteration_pool is original
    assert child.iteration_budget.consume()
    parent.iteration_budget = reset_iteration_budget(parent)
    assert parent._task_iteration_pool is not original
    assert parent._task_iteration_pool.used == 0
    # An older background child cannot start spending the new turn's pool.
    child.iteration_budget = reset_iteration_budget(child)
    assert child._task_iteration_pool is original
    assert child.iteration_budget.remaining == 1
    set_config_value("delegation.shared_iteration_limit", "0")
    parent.iteration_budget = reset_iteration_budget(parent)
    assert parent._task_iteration_pool is None
    assert parent.iteration_budget.remaining == 20
