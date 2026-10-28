# Offline search comparison: latest rerun

Measured on 27 October 2026, macOS ARM64, Python 3.14.9, Node 24.19.0,
tsx 4.23.15. This is a contributor-written synthetic component evaluation,
not an independent benchmark or an overall bot ranking. No model or network
calls occur in this offline run. Live MCP and the small Nous Portal memory
smoke test are reported separately in [ONLINE.md](ONLINE.md).

The optimized Hermes median is much closer to OpenBot, but **OpenBot remains
faster at all three catalog sizes**, including p95 in this run. At 1,024 tools,
Hermes is 1.562 ms versus OpenBot's 1.216 ms: a 0.346 ms median gap. No claim
of overall agent superiority follows from these results.

## Warm search latency

Milliseconds, p50 / nearest-rank p95 over 15 measured calls per query after two
warmups. All arms receive the same 128 queries and identical names, descriptions,
and full parameter schemas. The fixture digests match the earlier published run.
One benchmark process runs at a time, in a seeded order; no test suite or other
owned CPU workload ran alongside the final measurements.

| Catalog size | Hermes before cache p50 / p95 | Hermes optimized p50 / p95 | OpenBot p50 / p95 | Hermes median reduction |
|---|---:|---:|---:|---:|
| 32 | 0.144 / 0.164 | 0.079 / 0.171 | 0.047 / 0.061 | 44.9% |
| 256 | 0.910 / 0.975 | 0.374 / 0.401 | 0.300 / 0.398 | 58.9% |
| 1,024 | 3.858 / 6.056 | 1.562 / 2.918 | 1.216 / 1.511 | 59.5% |

The before arm here is the immediately preceding `b91a3b46` implementation,
which already has the earlier retrieval-quality fixes. This isolates the cache
and candidate-index change. It is not the older `6a3838d8` baseline from the
[initial scorecard](SCORECARD_INITIAL.md).

The boundary includes fresh per-call catalog construction, active registry
source classification, production ranking/projection, and neutral schema
extraction. It excludes import time, full bridge eligibility/dispatch, inference,
and tool execution. Immutable document metadata and corpus mathematics are
cached with explicit bounds; query answers, catalog entries, schemas and scope
authority are not cached. Eviction and cold initialization can have other costs.
These timings have no confidence intervals and do not predict whole-bot latency.

## Implementation-specific initial preparation

The receipt field `catalog_build_ms` records **one sample per arm/size** before
per-query warmups. The timed operations are different:

- Hermes calls production `build_catalog`: it snapshots active registry source
  labels, constructs search text, splits/stems words, and creates live catalog
  entries. Fixture definitions and registry registration precede this timer.
- OpenBot's adapter reshapes supplied fixture records and inserts them into the
  exported catalog array. Its production module import, original built-in
  catalog creation and schema initialization precede this timer. Its word
  processing and ranking occur during searches.

Hermes's corpus statistics and candidate index are also constructed lazily on
search, outside this initial-build timer. These numbers are therefore
**implementation-specific preparation diagnostics, not an equal-work startup
comparison**. They cannot establish a relative whole-agent startup speed. A
common-boundary time-to-first-usable-result distribution has not been measured.
Hermes's own recorded preparation cost did not improve in this run.

| Catalog size | Hermes before cache, ms | Hermes optimized, ms | OpenBot, ms |
|---|---:|---:|---:|
| 32 | 2.394 | 4.367 | 0.056 |
| 256 | 7.219 | 7.299 | 0.099 |
| 1,024 | 26.902 | 27.133 | 0.250 |

## Retrieval correctness

Counts are identical at all three sizes. Hermes before and after the latest
optimization return exactly the same names, order, and full schemas on all
384 query/catalog combinations, not merely the same pass counts.

| Measure | Hermes before cache | Hermes optimized | OpenBot |
|---|---:|---:|---:|
| Relevant tool in top five, supported queries | 112/112 | 112/112 | 112/112 |
| Relevant tool ranked first | 112/112 | 112/112 | 106/112 |
| Full relevant discovery schema | 112/112 | 112/112 | 104/112 |
| Request-wrapper variants retrieve a relevant tool | 60/60 | 60/60 | 60/60 |
| Unavailable-capability queries return no matches | 16/16 | 16/16 | 0/16 |

OpenBot returns partial keyword matches on the unavailable-capability controls.
This is a retrieval-policy difference, not proof it would execute the wrong tool
or fail a user task. No aggregate conformance score is presented as a bot win.
Schema completeness requires exact equality with the fixture JSON. These fixture
schemas are small; regression tests separately cover references and disclosure
budgets. The additional query variants were written by the contributor and are
not a blinded holdout. No retrieval criteria or fixture content changed to obtain
this speed result.

The initial quality run recorded 52/112 supported hits on `6a3838d8`, versus
112/112 after the earlier fixes. That historical result is retained with its
own measured revisions and timings in the initial scorecard; it is not silently
substituted for this run's before arm.

## Durable queue contracts

All three arms pass seven distinct contracts in three fresh subprocess
repetitions each (21/21 executions per arm): FIFO, persisted queued cancellation,
active-work cancellation refusal and late-completion fencing, queued restart
retention, honest active restart handling, recipient separation, and duplicate
replay. No queue production change was made for these cases.

Reopening is orderly, not power-loss testing. OpenBot's real mailbox explicitly
calls its conservative `recoverAsInterrupted` primitive, without testing its
boot/provider-history coordinator. Hermes leaves uncertain work unknown and
pauses followers; OpenBot marks it interrupted and permits followers. Both meet
the stated no-replay/no-false-completion contract. Setup-inclusive queue timings
are not advertised as throughput or agent speed.

## Provenance and receipts

- Hermes before: `b91a3b46c6fe0844de3939a33d90b1e4d85e02be`, an unchanged source archive.
- Optimized Hermes: `70a43eee415d6ee40e13ec0fe058f6422693f2ec`, clean tracked tree, no untracked entries.
- OpenBot: `f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe`, clean tracked tree and one disclosed dependency link.
- The actual Hermes registry is populated before timing. OpenBot's exported catalog
  data is injected; its ranking implementation is unchanged. No fixture tool is executed.
- [Protocol](README.md), [fixtures](fixtures.py), [runner](run.py).
- [Complete latest raw receipts](results/search-optimized.json.gz): all 18 planned
  launches completed, no runtime errors, no omitted or unfinished cases.
- Uncompressed receipt SHA-256: `1a28bf8f81861d79d84b1df4e393b215508e3adde9e3209e37d561e3877ae666`.
- Initial receipts and the abandoned nonexistent-profile diagnostic remain available
  via the initial scorecard. Intermediate development profiles were not used as final scores.

## Validation

The broader bot-reliability selection at `b91a3b46` passed **3,064 tests across
286 files, 0 failures, 15 platform skips**, retries disabled. After the search
change, all **196 targeted tests across 13 files** pass, including discovery,
registry, connectors, schema projection, scope/live updates, stable ties, exact
names, token mutations, and evaluation contracts. All **13 blocking repository
checks** pass. Earlier-source behavior probes retain their failing receipts;
the new memory behavior also has the explicitly limited live model smoke test.

The full repository suite and native Windows/Linux lanes were not run here.
Previously documented shell-wrapper failures also reproduce on unchanged upstream
source and remain outside these selections. A macOS path-alias assertion in the
expanded delegation selection reproduced on unchanged earlier code; the test now
compares resolved paths to the same database file. The final expanded selection
passes without file retries.

## Subsequent completion and recovery validation

A separate [before/after fault-contract run](TASK_RECOVERY.md) compares draft `789ac877` with `e748982b`: six distinct completion contracts improve from 4/6 to 6/6 in each of three fresh-process repeats. The invalid-reply write fixture gains an explicit unknown outcome; both versions commit one effect without replay. The broader updated selection passes 3,203 tests across 308 files, with 15 platform skips and no failures or file retries. These fixtures do not supply an OpenBot task-completion score or change the measured search timings above.

## Expanded native backend and Bot Mode evidence

[OPENBOT_BACKEND.md](OPENBOT_BACKEND.md) now exercises OpenBot's real service,
provider protocol and pinned Pi runtime. All five upstream-authored backend
scripts pass. The initial matched artifact test ties at five of six contracts.
Updated Hermes Bot Chats subsequently pass six of six; original Hermes and
OpenBot pass five of six, in three fresh-process repetitions each. The missing
output recovery is scripted, and already-complete file work costs one extra
model request. Forced concurrent-reply stability improves from 0/20 to 20/20 on
Hermes. The broader local selection passes 3,672 tests across 361 files, with
50 platform skips, no failures or retries. These results leave the earlier search
latencies unchanged and do not create an overall bot score. Native platform and
real-model task evidence is reported separately.
