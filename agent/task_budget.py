"""Optional shared ceiling on ordinary loop iterations across a delegated task.

This is not a physical-request or dollar cap: existing refunds, grace summaries,
auxiliary calls, SDK retries, and paid tools retain their existing semantics.
"""

from __future__ import annotations

from agent.iteration_budget import IterationBudget


class TaskIterationBudget(IterationBudget):
    def __init__(self, max_total: int, pool: IterationBudget):
        super().__init__(max_total)
        self.pool = pool

    def consume(self) -> bool:
        # Every operation takes the local lock before the pool lock. A sibling
        # cannot reserve beyond the shared ceiling between a check and increment.
        with self._lock:
            if self._used >= self.max_total or not self.pool.consume():
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        with self._lock:
            if self._used > 0:
                self._used -= 1
                self.pool.refund()

    @property
    def remaining(self) -> int:
        with self._lock:
            return min(max(0, self.max_total - self._used), self.pool.remaining)


def reset_iteration_budget(agent) -> IterationBudget:
    """New root turn, new pool; a child keeps the pool captured at construction."""
    pool = getattr(agent, "_inherited_task_iteration_pool", None)
    if not isinstance(pool, IterationBudget):
        from hermes_cli.config import load_config_readonly

        limit = (load_config_readonly().get("delegation") or {}).get(
            "shared_iteration_limit", 0
        )
        pool = IterationBudget(limit) if type(limit) is int and limit > 0 else None
    agent._task_iteration_pool = pool
    return (
        TaskIterationBudget(agent.max_iterations, pool)
        if pool is not None
        else IterationBudget(agent.max_iterations)
    )


def inherit_task_budget(child, parent) -> None:
    pool = getattr(parent, "_task_iteration_pool", None)
    if isinstance(pool, IterationBudget):
        child._inherited_task_iteration_pool = pool


def task_budget_result_fields(agent) -> dict:
    pool = getattr(agent, "_task_iteration_pool", None)
    if not isinstance(pool, IterationBudget):
        return {}
    return {
        "task_iteration_budget": {
            "limit": pool.max_total,
            "used": pool.used,
            "scope": "shared_ordinary_loop_iterations",
            "physical_request_cap": False,
        }
    }
