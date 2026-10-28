"""Required worktree setup and initial cwd binding for delegated workers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("tools.delegate_tool")


class RequiredIsolationError(RuntimeError):
    """Refuse execution when a requested worktree could not be established."""


def create_workspace(
    parent: Any, parent_task_id: Any, child_id: str | None, mode: bool | str
):
    if not mode:
        return None
    required = mode == "required"
    from tools import subagent_worktree
    from tools.delegate_tool import _resolve_workspace_hint
    from tools.terminal_tool import get_session_cwd

    if not subagent_worktree.local_backend_active():
        if required:
            raise RequiredIsolationError(
                "Required worktree isolation is unavailable on the active terminal backend."
            )
        return None
    try:
        parent_cwd = get_session_cwd(parent_task_id)
    except Exception as exc:
        if required:
            raise RequiredIsolationError(
                "The parent workspace could not be resolved; required delegated execution was refused."
            ) from exc
        parent_cwd = None
    try:
        info = subagent_worktree.create_subagent_worktree(
            parent_cwd or _resolve_workspace_hint(parent),
            subagent_id=child_id,
        )
    except Exception as exc:
        if required:
            raise RequiredIsolationError(
                "Required worktree creation failed; delegated execution was refused."
            ) from exc
        logger.warning("Best-effort worktree creation failed: %s", exc)
        return None
    if info is None and required:
        raise RequiredIsolationError(
            "Required worktree isolation needs a committed local Git repository; delegated execution was refused."
        )
    if info is not None and required:
        info["isolation_mode"] = "required"
    return info


def bind_workspace(info: dict[str, str], child: Any, child_task_id: str) -> None:
    from tools.delegate_tool_routes import child_profile_scope
    from tools.terminal_tool import get_session_cwd, record_session_cwd

    required = info.get("isolation_mode") == "required"
    try:
        with child_profile_scope(child):
            record_session_cwd(child_task_id, info["path"])
            if (
                required
                and Path(get_session_cwd(child_task_id)).resolve()
                != Path(info["path"]).resolve()
            ):
                raise RequiredIsolationError(
                    "Required worktree cwd binding was not retained; delegated execution was refused."
                )
        if required:
            info["cwd_verified"] = "true"
    except Exception as exc:
        if required:
            raise RequiredIsolationError(
                "Required worktree cwd binding failed; delegated execution was refused."
            ) from exc
        logger.warning("Best-effort worktree cwd binding failed: %s", exc)
