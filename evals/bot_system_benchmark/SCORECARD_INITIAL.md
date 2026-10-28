# Offline component comparison: Hermes and OpenBot.run

Measured on 27 October 2026 on macOS ARM64, Python 3.14.9, Node v24.19.0 and tsx 4.23.15.
This is a contributor-written synthetic component suite, with 88 initial cases and 40 additional request variants.
It is not an independent benchmark or a blinded holdout. No model or API calls were made.

Both systems retrieved a relevant tool for every supported query and passed the queue contracts.
Hermes ranked more relevant tools first and supplied more intact schemas. OpenBot was faster at every tested catalog size.
These results establish component behavior; they do not establish overall bot superiority or higher real-task completion rates.

## Discovery behavior

Each size (32, 256 and 1,024 tools) produced the same counts below. The 112 supported queries and 16 unavailable-capability queries are reported separately.

| Measure | Hermes before | Hermes updated | OpenBot |
|---|---:|---:|---:|
| Relevant tool in first five results | 52/112 | 112/112 | 112/112 |
| Relevant tool ranked first | 52/112 | 112/112 | 106/112 |
| Intact parameter schema supplied for a relevant result | 0/112 | 112/112 | 104/112 |
| Request-wrapper variants retrieve a relevant tool | 0/60 | 60/60 | 60/60 |
| Unavailable-capability queries return no matches | 16/16 | 16/16 | 0/16 |

OpenBot returns partial keyword matches for the unavailable-capability queries. Hermes deliberately requires the query's intent terms.
The empty-result control measures that policy difference. It does not prove that OpenBot would execute an incorrect tool or fail a user task.
The raw aggregate conformance counts are retained in the receipts, but are not presented as an agent leaderboard.
Returned schemas were compared with the complete fixture JSON, rather than counted from field presence alone.
The fixture schemas are small; separate regression tests cover schema budgets, references and invalid payloads.

## Discovery latency

Milliseconds, shown as p50 / p95 over 15 measured calls per query after two warmups.
Arm order uses seed 20261027. Only one benchmark process ran at a time.
The boundary includes the real search and result projection, Hermes's stateless catalog build/source classification, and neutral schema extraction.
It excludes report serialization, process import time, provider inference, full bridge eligibility/dispatch and tool execution.

| Catalog size | Hermes before p50 / p95 | Hermes updated p50 / p95 | OpenBot p50 / p95 | Observed Hermes p50 reduction |
|---|---:|---:|---:|---:|
| 32 | 0.373 / 0.544 | 0.142 / 0.156 | 0.050 / 0.098 | 62.0% |
| 256 | 3.031 / 3.612 | 0.909 / 1.066 | 0.309 / 0.436 | 70.0% |
| 1,024 | 12.447 / 19.114 | 3.756 / 4.362 | 1.287 / 1.778 | 69.8% |

OpenBot retains lower local discovery latency. Hermes's observed improvement is relative to its own previous version.
These are host-specific timings over a synthetic workload, without confidence intervals or a multi-host campaign.
They do not predict full agent latency or model cost.

## Durable queues

All three arms passed seven contracts in each of three subprocess repetitions: FIFO order, persisted queued cancellation,
active queued-cancellation refusal and late-completion fencing, queued restart retention, honest active restart recovery,
recipient separation and idempotent replay. That is 21/21 contract executions per arm, covering seven distinct behaviors.
No queue production patch was added because these contracts showed parity.

These tests reopen SQLite stores in an orderly manner. They do not simulate SIGKILL, power loss, external side effects or live provider reconnection.
OpenBot's test explicitly invokes its conservative `recoverAsInterrupted` store primitive; its boot/provider-history coordinator is outside the test.
Hermes leaves uncertain work unknown and pauses followers; OpenBot marks it interrupted and permits the follower.
Both policies pass the stated no-replay/no-false-completion contract. Queue durations include database setup and are not advertised as throughput.

## Provenance and reproducibility

- Hermes before: `6a3838d8c9d4c9788f25721825dcd4cf80d76692`, an unchanged source archive of the earlier draft-PR implementation.
- Hermes measured implementation: [`9101b71e`](https://github.com/itsflownium/hermes-agent/commit/9101b71ee5b7eb2e6939368de5c72327dd5e3089).
- OpenBot source: [`f91535fb`](https://github.com/nightly-labs/openbot/tree/f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe).
- Both tracked source trees were clean. OpenBot had one untracked runtime dependency link, disclosed by the metadata.
- Both systems received identical names, descriptions, schemas and query order. Hermes's fixture populated a fresh actual registry outside timing;
  OpenBot's fixture replaced only its exported catalog array. Neither engine's ranking implementation was replaced and no fixture handler was invoked.
- Existing empty temporary profiles allow normal scope-key caching. Environments exclude credentials and user configuration.
- [Protocol and setup](README.md), [fixtures](fixtures.py), and [runner](run.py).
- [Full final receipts](results/final.json.gz): all 18 planned launches completed, with no runtime errors or omitted cases.

An earlier setup diagnostic pointed at a nonexistent Hermes home, preventing normal scope-key caching and inflating lookup cost.
It was stopped and excluded from performance interpretation. Its eight admissions (six completed, one timeout and one unfinished) out of 18 planned launches
remain in the [setup diagnostic receipts](results/setup-diagnostic.json.gz), explicitly marked `aborted_setup_issue` and invalid for performance.
Development smoke tests and that diagnostic are separate from the final experiment.

The final uncompressed receipt SHA-256 is `4a45b25fc59be352bbb3a2b6245b348850d61dbb53ca0096d08e76d3c5c0f405`.
The gzip files preserve the complete JSON and contain no source checkout paths or credentials.

## Implementation validation

The measured code passed the canonical regression selection: **1,514 passed, 0 failed, 8 platform skips across 139 files**, with retries disabled.
All **13 blocking repository checks** passed. New discovery behavior tests fail five cases on the earlier source and retain a passing cache-isolation control.
Registry work-bound regressions fail on the earlier implementation (96/97 scope resolutions) and pass with the fresh snapshot; scope/live-update controls pass both.
The entire repository suite and native Windows/Linux runs were not executed on this Mac.

Previously documented shell-wrapper failures in `tests/tools/test_terminal_pipeline_status.py` also reproduce on unchanged upstream source and remain outside this selection.
No model-driven task benchmark, mobile/desktop user study, real network connector action, or learning-quality evaluation is included.
