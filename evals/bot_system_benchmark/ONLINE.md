# Live component checks and targeted memory smoke test

These results complement the [offline protocol](README.md). They do not produce
an overall agent score. The live MCP comparison uses OpenBot's actual backend;
no desktop UI or model-backed OpenBot conversation was exercised.

## Public MCP checks

Both implementations connected to the same public, no-auth Streamable HTTP
servers, listed tools, and closed their connections. No remote tools, inference,
OAuth flows, or private user data were used. A third endpoint was an ordinary
webpage that should be rejected. Each case was repeated three times in fresh
processes, sequentially in a fixed shuffled order.

| Case | Hermes | OpenBot backend |
|---|---:|---:|
| DeepWiki connection and discovery (3 tools) | 3/3 | 3/3 |
| GitMCP connection and discovery (4 tools) | 3/3 | 3/3 |
| Reject a non-MCP webpage without exposing tools | 3/3 | 3/3 |

The sources are [`MCPServerTask` / `_connect_server`](../../tools/mcp_tool_discovery.py)
and OpenBot's `src/backend/mcp-probe.ts::inspectMcpServer` at
`f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe`. Hermes source was `b91a3b46`
with a clean tracked tree. The new measurement adapters were supplied separately;
their digests are in the receipt. The observation validator was subsequently
extracted into a helper, and every raw observation was revalidated with the
published helper without changing any outcome.

All 18 planned launches completed. This establishes compatibility in these
connections, not a long-run reliability rate. Hermes' persistent lifecycle and
OpenBot's probe do different ancillary work, so the recorded times are not used
as a speed ranking. Actual remote tool execution, authentication, reconnection,
failure recovery, and task completion remain unmeasured here.

One setup diagnostic had six OpenBot adapter transformation failures before
network I/O because the initial script was executed as CommonJS. It is retained
and **is not counted as an OpenBot product failure**. An initial corrected run
also completed all 18 launches successfully and is retained separately.

Raw receipts, compressed with gzip:

- [Published harness run](results/public-mcp-final.json.gz), uncompressed SHA-256
  `15868d33312f1ca6fe263dc304ea4613d8394722f738df1d9a5595d7825b795d`.
- [Initial corrected run](results/public-mcp-initial-verified.json.gz).
- [Setup diagnostic](results/public-mcp-setup-diagnostic.json.gz).

The [DeepWiki documentation](https://docs.devin.ai/work-with-devin/deepwiki-mcp)
and [GitMCP repository](https://github.com/idosal/git-mcp) identify the services;
the receipt records the tool names actually observed. A mutable public service
can change between runs.

To reproduce, provision the external OpenBot dependencies as in the offline
README, then explicitly opt into network access by running:

```bash
"$BENCH_PYTHON" evals/bot_system_benchmark/run_mcp.py \
  --hermes "$BENCH_HERMES_SRC" --openbot "$BENCH_OPENBOT_SRC" \
  --node "$BENCH_NODE" --tsx-loader "$BENCH_TSX_LOADER" \
  --output "$BENCH_MCP_RECEIPT"
```

Output paths must be new. Process failures, malformed observations, timeouts,
and admitted-but-unfinished launches remain visible. A process failure cannot
pass the non-MCP rejection control. The script writes stderr sidecars for local
diagnostics; inspect them before sharing.

## DeepSeek through Nous Portal: native memory

This is one contributor-written, three-turn conversation per revision using the
real `AIAgent`, with the requested model `deepseek/deepseek-v4.1-flash` through
the existing Nous Portal account. It is a small smoke test, not an independent
benchmark. OpenBot was not included in this model-backed test.

Each agent used a fresh temporary profile and workspace, no tool schemas,
no project context files, no background review, and no fallback model. The same
question asked for the current native-memory interval or `UNKNOWN` if absent.
The harness changed the real memory file between turns. Expected answers were
declared before either conversation; the updated arm ran first in the seeded
order. Every launch and turn is retained.

| Native state | Expected | Earlier Hermes (`6a3838d8`) | Updated Hermes (`b91a3b46`) |
|---|---|---|---|
| Preferred interval is 17 minutes | `17` | `17` | `17` |
| Another writer changes it to 43 minutes | `43` | `17` | `43` |
| Another writer deletes the native entry | `UNKNOWN` | `17` | `UNKNOWN` |

Earlier Hermes passed 1/3 assertions; updated Hermes passed 3/3. Each arm's
system/developer prefix hash stayed identical across all three turns, and all
prior message rows remained unchanged. The current version's correction and
deletion notes appeared on user-message content behind that stable prefix.
Deleting a native entry does not erase past conversation text or certify erasure
from backups or external providers.

The adapter observed three request builds per revision. SDK retries were disabled,
output was capped at 1,024 tokens per request, and the harness allowed at most
six builds per revision. Dollar cost was not supplied by this receipt and is
reported as unknown; no separate DeepSeek or OpenRouter key was used.

The [raw memory receipt](results/portal-memory-smoke.json.gz) includes the plan,
answers, prefix hashes, observations, and the exact as-run adapter source.
Uncompressed SHA-256:
`1d755cbfdd659635f09651a3d7ee006a65b4060e2efd44b2c0c4c829b7e6b1ae`.
Local source locations were redacted from launch metadata. The command-line
probe is [memory_portal.py](memory_portal.py); its later function wrapper and
formatting do not change the tested request or observation logic.

To reproduce, sign into Nous Portal using the normal Hermes flow, then pass a
JSON object on stdin to `memory_portal.py` with `repository`, a new `output`
path, and these `cases`:

```json
[
  {"id": "initial_native_fact", "state": "Preferred reminder interval: 17 minutes.\n", "expected": "17"},
  {"id": "external_native_correction", "state": "Preferred reminder interval: 43 minutes.\n", "expected": "43"},
  {"id": "external_native_deletion", "state": null, "expected": "UNKNOWN"}
]
```

This command makes model requests through the signed-in Portal account. It is
separate from the zero-model-spend public MCP runner and never runs in unit CI.
