# Bot system component benchmark

Runs real Hermes and OpenBot discovery functions and durable queue stores on
identical synthetic inputs, without model calls, accounts, or network access
during measurement. It measures component behavior and local overhead. It does
not measure reasoning quality, desktop usability, or overall agent superiority.

The default `run.py` remains offline. Explicit public network checks and a small
Nous Portal memory smoke test are documented separately in [ONLINE.md](ONLINE.md).

The OpenBot implementation is imported from a separately supplied checkout.
No competitor implementation is copied into this repository. Its license and
the license of every runtime dependency still apply to those external sources.

## Protocol

- Discovery has 88 initial cases and 40 separately reported additional
  request variants. This is a transparent synthetic suite, not a blinded holdout.
  Each implementation receives the same names, descriptions,
  parameter schemas and query order. Catalog sizes are 32, 256 and 1,024.
- Report positive-query hit@5, top-1, complete parameter schemas in results,
  and empty results for unavailable capabilities separately by case group.
  Returned parameter schemas must equal the fixture in full; field presence
  alone is not accepted as schema readiness.
  The total is a component conformance count, not an agent leaderboard score.
- Both adapters run the actual production search and result projection. Hermes
  registers the fixture in a fresh real tool registry before measurement and
  includes its per-call catalog rebuild and source classification. The registry
  size is reported; the setup does not time an empty registry as a loaded one.
  OpenBot replaces only its exported
  catalog data; ranking, query validation, schema selection and guidance remain
  unchanged. Import time is excluded from per-query latency and included in
  process wall time. Neither adapter invokes a deferred tool.
- The single `catalog_build_ms` diagnostic has unequal work boundaries:
  Hermes runs its production source-label/tokenization/catalog build; OpenBot's
  adapter maps and inserts fixture records after importing the production module.
  It is not a comparative agent-startup measurement. See the scorecard for the
  exact boundaries; the per-query timing and fixture criteria are separate.
- Two warmups and 15 measured calls per query produce raw timing samples,
  median and nearest-rank p95. Arm order uses a fixed random seed. Processes
  run sequentially; timings are host-specific and have no inference component.
- Queue cases cover FIFO order, persisted cancellation, refusal of queued
  cancellation for active work, late completion fencing, reopening queued and
  active work, recipient separation and idempotent replay. Each case creates
  a fresh real SQLite store. Three subprocess repetitions are retained.
- Queue timing includes database setup and all case operations. It is not
  steady-state queue throughput or agent speed. Reopening is orderly; these
  tests do not simulate power loss or prove fsync durability.
- Hermes calls its runtime epoch/recovery authority. OpenBot reopens its real
  mailbox and explicitly invokes conservative `recoverAsInterrupted` when
  provider history is unavailable. This does not test its boot coordinator or
  live provider reconciliation. Their different follower policies are recorded,
  rather than scored as a failure when neither replays uncertain work.
- The full planned launch count and running/completed state are recorded before
  measurement. Every launch is checkpointed before execution. Timeouts, invalid output,
  runtime errors, unfinished starts and unsupported cases remain visible.
  Credentials are excluded from subprocess environments; state is temporary.
  The isolated Hermes home exists before import, matching a provisioned profile
  and allowing the normal scope-key cache. A nonexistent-home diagnostic is not
  comparable performance evidence and must be reported separately.

The fixture files contain the acceptance criteria. The report contains their
SHA-256 digest, adapter digests, source revisions, all raw observations and all
latency samples. No failures or unavailable-capability controls are discarded.

## Setup and run

Use the repository's prepared test Python environment for Hermes. Supply a
Node 24 runtime and a separately installed TypeScript loader. OpenBot's pinned
backend needs these production packages for the selected import graph:

| Package | Version |
|---|---|
| `effect` | `4.0.6` |
| `zod` | `4.6.7` |
| `yaml` | `2.9.1` |
| `@modelcontextprotocol/sdk` | `1.32.1` |
| `emoji-regex` | `10.6.0` |
| `ts-log` | `3.0.3` |
| `fflate` | `0.8.3` |
| `marked` | `18.1.1` |
| `tsx` (measurement loader) | `4.23.15` |

Install them in a disposable runtime directory with package scripts disabled.
Link its `node_modules` into the external OpenBot checkout, and link that
checkout's `packages/*` workspaces under `node_modules/@openbot/` using each
package's declared name. Do not replace an existing runtime or change user
state. This provisions only the tested backend import graph, not the desktop
application or the provider CLIs. OpenBot source revision used in this run:
[`f91535fb`](https://github.com/nightly-labs/openbot/tree/f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe).

Set the `BENCH_*` variables below to your external source and runtime locations.
`BENCH_BEFORE_SRC` must contain the unchanged Hermes revision indicated by
`--before-revision`; a source archive is accepted. The latest speed rerun uses
`b91a3b46c6fe0844de3939a33d90b1e4d85e02be`; the initial quality comparison uses
`6a3838d8c9d4c9788f25721825dcd4cf80d76692`. Set `BENCH_BEFORE_REVISION` to match the supplied source.

```bash
"$BENCH_PYTHON" evals/bot_system_benchmark/run.py \
  --python "$BENCH_PYTHON" \
  --node "$BENCH_NODE" \
  --tsx-loader "$BENCH_TSX_LOADER" \
  --hermes-source "$PWD" \
  --before-source "$BENCH_BEFORE_SRC" \
  --before-revision "$BENCH_BEFORE_REVISION" \
  --openbot-source "$BENCH_OPENBOT_SRC" \
  --openbot-revision f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe \
  --output "$BENCH_RECEIPTS"
```

To compare agent task performance, a separate run must control model version,
reasoning effort, provider/runtime route, tools, permissions, spending and time
limits, and grade final artifacts against predeclared outcomes. Those results
must not be inferred from this offline component benchmark.

Completion/recovery changes also have a separate [fixed fault-contract protocol and receipts](TASK_RECOVERY.md). These real-agent/local-transport probes use scripted responses and provide no overall OpenBot task score.

The expanded [OpenBot native-backend comparison](OPENBOT_BACKEND.md) additionally
runs upstream-authored service/provider recovery tests, the actual pinned Pi
runtime on matched artifact cases, original Hermes and the Bot Chat completion
and first-reply fixes. All initial failures and request overhead are disclosed.
Actual model-driven tasks have a separate [fixed protocol](MODEL_TASKS.md).
