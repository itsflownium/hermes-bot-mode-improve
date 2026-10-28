"""Opt-in public network checks; no inference, auth headers, or remote tool execution."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time

if __package__:
    from .mcp_common import classify
else:
    from mcp_common import classify

HERE = Path(__file__).resolve().parent
ENDPOINTS = (
    {
        "id": "deepwiki",
        "url": "https://mcp.deepwiki.com/mcp",
        "expected": "catalog",
        "source": "https://docs.devin.ai/work-with-devin/deepwiki-mcp",
    },
    {
        "id": "gitmcp",
        "url": "https://gitmcp.io/idosal/git-mcp",
        "expected": "catalog",
        "source": "https://github.com/idosal/git-mcp",
    },
    {
        "id": "non_mcp",
        "url": "https://example.com/",
        "expected": "reject",
        "source": "https://www.iana.org/domains/reserved",
    },
)
_ENV_KEYS = {
    "PATH",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
}


def _attempt(args, item: dict, number: int) -> dict:
    arm = item["implementation"]
    command = (
        [sys.executable, str(HERE / "mcp_hermes.py")]
        if arm == "hermes"
        else [
            str(args.node),
            "--import",
            str(args.tsx_loader),
            str(HERE / "mcp_openbot.mts"),
        ]
    )
    row = {**item, "attempt": number, "admitted_at": datetime.now(UTC).isoformat()}
    with tempfile.TemporaryDirectory(prefix="public-mcp-") as directory:
        state = Path(directory)
        home = state / "home"
        home.mkdir()
        env = {key: value for key, value in os.environ.items() if key in _ENV_KEYS}
        env.update(
            HOME=str(home),
            HERMES_HOME=str(home),
            HERMES_RUNTIME_DIR=str(state / "runtime"),
            TZ="UTC",
        )
        repository = args.hermes if arm == "hermes" else args.openbot
        request = {
            "repository": str(repository),
            "url": item["endpoint"]["url"],
            "timeout_seconds": args.timeout,
        }
        started = time.perf_counter()
        try:
            process = subprocess.run(
                command,
                input=json.dumps(request),
                text=True,
                capture_output=True,
                check=False,
                env=env,
                cwd=repository,
                timeout=args.timeout + 25,
            )
            stderr = args.output.with_name(
                f"{args.output.stem}-attempt-{number:02d}.stderr.txt"
            )
            stderr.write_text(process.stderr)
            row.update(
                returncode=process.returncode,
                stderr_sha256=hashlib.sha256(process.stderr.encode()).hexdigest(),
                **classify(
                    process.returncode, process.stdout, item["endpoint"]["expected"]
                ),
            )
        except subprocess.TimeoutExpired:
            row.update(status="process_timeout", contract_pass=False)
        except OSError as exc:
            row.update(
                status="launch_error",
                contract_pass=False,
                error_class=type(exc).__name__,
            )
        row["process_wall_ms"] = (time.perf_counter() - started) * 1000
    return row


def run(args) -> dict:
    plan = [
        {"endpoint": dict(endpoint), "implementation": arm, "repetition": repetition}
        for endpoint in ENDPOINTS
        for repetition in range(args.repetitions)
        for arm in ("hermes", "openbot")
    ]
    random.Random(args.seed).shuffle(plan)
    receipt = {
        "schema_version": 2,
        "started_at": datetime.now(UTC).isoformat(),
        "seed": args.seed,
        "timeout_seconds": args.timeout,
        "planned_attempts": plan,
        "attempts": [],
        "sources": {},
        "model_spend_usd": 0,
        "scope": "Public no-auth MCP handshake, tool listing and orderly close; no inference or tool calls.",
        "limits": "Hermes lifecycle and OpenBot inspectMcpServer do different ancillary work. Timings do not establish a speed ranking; three repetitions do not establish reliability rates.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(receipt, handle, indent=2)
    for arm, repository in (("hermes", args.hermes), ("openbot", args.openbot)):
        receipt["sources"][arm] = {
            "revision": subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True, timeout=10
            ).strip(),
            "tracked_diff_sha256": hashlib.sha256(
                subprocess.check_output(
                    ["git", "-C", str(repository), "diff", "HEAD", "--binary"], timeout=10
                )
            ).hexdigest(),
            "tracked_dirty": bool(
                subprocess.check_output(
                    ["git", "-C", str(repository), "diff", "HEAD", "--name-only"], timeout=10
                )
            ),
        }
    receipt["adapters_sha256"] = {
        name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        for name in ("mcp_hermes.py", "mcp_openbot.mts", "mcp_common.py", "run_mcp.py")
    }
    args.output.write_text(json.dumps(receipt, indent=2))
    for number, item in enumerate(plan, 1):
        receipt["attempts"].append({**item, "attempt": number, "status": "admitted"})
        args.output.write_text(json.dumps(receipt, indent=2))
        row = _attempt(args, item, number)
        receipt["attempts"][-1] = row
        args.output.write_text(json.dumps(receipt, indent=2))
        print(
            f"{number}/{len(plan)} {item['implementation']} {item['endpoint']['id']}: {row['status']} pass={row['contract_pass']}",
            flush=True,
        )
    receipt["completed_at"] = datetime.now(UTC).isoformat()
    args.output.write_text(json.dumps(receipt, indent=2))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("hermes", "openbot", "node", "tsx-loader", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--repetitions", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--timeout", type=int, choices=range(1, 61), default=10)
    parser.add_argument("--seed", type=int, default=20261027)
    args = parser.parse_args()
    for name in ("hermes", "openbot", "node", "tsx_loader", "output"):
        setattr(args, name, getattr(args, name).resolve())
    run(args)


if __name__ == "__main__":
    main()
