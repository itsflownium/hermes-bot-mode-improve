"""Conservative path coverage for targeted verification commands."""

import re
from pathlib import Path

from agent.verification_snapshot import normalize_paths


_VALUE_FLAGS = frozenset({
    "--junitxml", "--junit-xml", "--log-file", "--basetemp", "--tb", "--color",
    "--maxfail", "-n", "--numprocesses", "-j", "--jobs", "-r", "--capture",
    "--file-timeout", "--file-retries", "--durations", "--durations-min",
})
_REPORTING_FLAGS = frozenset({
    "-s", "-x", "--exitfirst", "--quiet", "--verbose", "--disable-warnings",
    "--disable-pytest-warnings", "--no-header", "--no-summary", "--showlocals", "--full-trace",
    "--strict-markers", "--strict-config",
})


def _redirect_width(argument: str) -> int:
    match = re.fullmatch(r"\d*(?:>>?|<<?|>&|<&)\s*(.*)", argument)
    return (1 if match[1] else 2) if match else 0


def _path_target(argument: str, cwd: str | Path) -> bool:
    path = Path(cwd) / argument
    return bool(path.suffix or path.exists() or argument.startswith(("test_", "tests", "spec", "__tests__"))
                or any(marker in argument for marker in ("/", "\\")))


def _trailing_targets(arguments: list[str], cwd: str | Path) -> tuple[list[str], bool]:
    targets: list[str] = []
    filtered = False
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        flag = argument.split("=", 1)[0]
        redirect = _redirect_width(argument)
        if redirect:
            index += redirect
            continue
        if flag in _VALUE_FLAGS:
            index += 2 if flag == argument else 1
            continue
        if argument == "--" or argument in _REPORTING_FLAGS or re.fullmatch(r"-(?:[qv]+|r[AaEfFpsxXw]+)", argument):
            index += 1
            continue
        if argument.startswith("-") or "::" in argument or "=" in argument or not _path_target(argument, cwd):
            filtered = True
        else:
            targets.append(argument)
        index += 1
    return targets, filtered


def command_scope(arguments: list[str], *, cwd: str | Path, root: str | Path) -> tuple[str, tuple[str, ...]]:
    """A file/path target covers only that path; name selectors prove no whole-file scope.

    Test-to-source relationships require repository knowledge this ledger does not have.
    Output paths and option values must never be mistaken for verified inputs.
    """
    targets, filtered = _trailing_targets(arguments, cwd)
    base = Path(cwd).resolve()
    workspace = Path(root).resolve()
    targeted = filtered or bool(targets) or base != workspace
    if not targeted:
        return "full", ()
    if filtered:
        return "targeted", ()
    return "targeted", tuple(normalize_paths(targets or [str(base)], root=workspace, cwd=base))
