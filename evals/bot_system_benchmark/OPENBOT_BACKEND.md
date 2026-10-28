# OpenBot backend evaluation

This extends the earlier discovery/store/probe comparison through OpenBot's real
agent service, provider driver, SQLite persistence and its pinned Pi executable.
It does not test the desktop UI or use paid inference. No OpenBot production
implementation is copied into Hermes or replaced with a mock.

## Boundaries and fixed protocol

OpenBot source is `f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe`, exported from Git.
Use its exact native-runtime-lock binaries: Bun 1.4.4 and Pi 1.1.0 on macOS arm64.
Verify the release archive/binary SHA-256 values before executing them. Install
the required backend import graph in a separate runtime with package scripts
disabled; workspace links point to the unchanged external source archive.

First run these unchanged upstream scripts sequentially, retaining each native
report: provider conformance, recorded transcript replay, stuck-delivery recovery,
provider-exit/session handling and Pi steering. These scripts supply controlled
provider processes; their assertions belong to OpenBot. Report the supported and
uncovered providers explicitly, without turning a script count into a task score.

The matched artifact phase uses actual AIAgent/file tools for Hermes, and actual
AgentService/PiAgentClient/Pi file tools for OpenBot. Both use the same local HTTP
server with predeclared response sequences. The endpoint generates OpenAI-format
responses; it does not call an inference provider. The tool-name mapping is
`write_file`/`read_file` for Hermes and `write`/`read` for Pi, with the same logical
relative paths and file bytes. Each arm gets its normal prompt/tool surface for
this test; these are different implementations, not identical model contexts.

Neither arm gets a preloaded checklist or an injected checklist tool call.
Hermes's checklist tool remains available. These cases therefore do not repeat
the favorable prerequisite in the earlier Hermes-only completion fixtures.

| Fixed case | Supplied response sequence | Acceptance oracle |
|---|---|---|
| Complete files | Write report, write attachment, final answer | Exact bytes REPORT and ATTACHMENT |
| Premature final | Write report, premature final; attachment write available only if runtime continues | Both exact files exist when the accepted user turn ends |
| Blocked | Explain missing input | No fabricated files; blocker stated |
| Cancelled | Acknowledge user's cancellation | No output files; cancellation stated |
| Status only | Read an existing report, answer | ORIGINAL bytes unchanged; no attachment created |
| File-write recovery | Write to an existing directory (error), correct path, write both files, final | Error visible in the tool result and both exact output files |

Run each case in each arm in three fresh processes, sequentially in a fixed
shuffled order (seed 20261027): 36 planned launches. A run checkpoints its complete
plan and each admission before execution. Keep timeouts, errors and failed
contracts; there is no best-of selection or file retry. The worker deadline is
100 seconds, with an 80-second inner OpenBot process bound. A fixture that invokes
an unadvertised tool is a setup error, not an agent task failure.

Record observed file bytes, saved final responses, queue/turn outcomes, request
counts, tool results, request/message/schema hashes and all launches. Omit HTTP
authorization headers and production system-prompt text. This preserves the
observations and provenance without publishing credentials or redistributing
OpenBot's prompt content. Runtime state stays in temporary directories.

These are authored, unblinded fault/contract cases. Scripted responses test runtime
behavior, not a model's ability to choose actions, search, reason or solve a user
task. Provider-native work differs from a Hermes model/tool loop. Request counts
are diagnostic, not a comparable dollar-cost or latency ranking. Report each case
and every unsupported area; do not combine these with search into an overall bot
score. The test does not establish which product is best.

## Setup diagnostics

The initial local Bun 1.3.14 could not load `node:sqlite`; five script launches
failed before their tests started and produced no reports. Retain these as setup
diagnostics. The compatible pinned Bun is required for the measured upstream run.
An adapter pilot with an empty initial message was refused by the real service;
the adapter uses its required initial-message creation flow before graded runs.

## Subsequent Bot Mode improvement cycle

The initial six shared cases also run in real managed Bot Chat sessions, using
an actual profile marker, SessionDB title and desktop surface. The before arm is
an unchanged `00a8b6b2` archive; verify its tracked Python blobs. The after arm is
a clean implementation commit. The unchanged OpenBot/Pi arm is included again:
54 launches, six cases, three variants, three fresh-process repetitions, fixed
shuffle seed 20261027. Use `run_bot_mode_cycle.py`. Completed sequences repeat
their last scripted final answer if a runtime asks for a review; premature-final
sequences retain the already-declared continuation with the missing file write.
These follow-up responses are supplied equally to every arm.

Record the review's extra request overhead explicitly. Do not attribute a native
runtime's continuation to a real model's reasoning quality. Further real Bot Chat
regressions use JSON/CSV and Markdown/TSV/JSON deliverables, no checklist, next-turn
reset, stable message prefix/schemas, disabled config, ordinary chats, reads and
an exhausted iteration allowance. These are additional authored cases, not a
blinded holdout. Preserve the initial common-case failure receipts.

A separate `run_relay_settlement.py` run tests the first reply race with two real
processes. Both reach the publication boundary before the first is released; the
second resumes only after the first result has been read. Run both outcome orders
(answer before error, error before answer), ten fresh-process repetitions per arm:
40 launches. Compare the first observed bytes with the final bytes; a changed reply
is a failure. This uses the same filesystem-write wrapper in both implementations,
not fake filesystem results. The old archive receives only the new probe test
module. Production files stay unchanged. Failed stage/link operations and separate
envelope controls run through the canonical test runner. No OpenBot
score is inferred from this Hermes-specific publication contract.

## Untouched upstream baseline

After the three-variant cycle, `run_original_baseline.py` adds the original
Hermes upstream revision `c714c42431e518fcd1c8870eff5c667d5de33b57` to the same
six fixed cases. Verify every tracked Python blob against Git before and after.
Use an unchanged source archive, the same scripted endpoint/tool adapter, actual
managed Bot Chat identity, three fresh-process repetitions per case and shuffle
seed 20261027: 18 additional launches. No response sequence or acceptance rule
changes. This is an additional baseline, not a replacement of the earlier
admissions. It measures these runtime contracts; it does not create a general
percentage improvement over original Hermes.

## Measured results, 27 October 2026

OpenBot's unchanged upstream scripts all pass: provider conformance (six ACP
provider adapters), one recorded released-CLI transcript replay, nine stuck-delivery
recovery scenarios, provider-exit/session preservation and Pi steering. The raw
report lists providers outside conformance coverage. These are upstream-authored
scripted provider tests, not five general task-success samples. The separate
matched tests below run the actual pinned Pi executable and native file tools.

The first matched core-loop run at `00a8b6b2` passed five of six distinct contracts
in both Hermes and OpenBot: each arm passed 15/18 executions. Both missed the
attachment after a premature final response in all three repetitions. This
unfavorable common result is retained in full. No checklist prelude was supplied.

The subsequent managed Bot Chat run compares unchanged draft `00a8b6b2`, clean
implementation `bb25e548` and unchanged OpenBot. The original upstream archive
`c714c424` was also tested in 18 additional launches with identical fixed inputs,
responses and grading. Every tracked Python blob was verified against Git. All
108 launches across these three artifact phases completed, without worker errors,
fixture errors or timeouts. Repetitions are checks of reproducibility.

| Fixed contract, three fresh-process repeats | Original Hermes | Previous draft | Updated Hermes Bot Chat | OpenBot/Pi |
|---|---:|---:|---:|---:|
| Both files already complete | 3/3 | 3/3 | 3/3 | 3/3 |
| Premature final: both files must exist | 0/3 | 0/3 | 3/3 | 0/3 |
| Missing input: explain blocker | 3/3 | 3/3 | 3/3 | 3/3 |
| Cancelled request: no files | 3/3 | 3/3 | 3/3 | 3/3 |
| Read-only status: existing bytes preserved | 3/3 | 3/3 | 3/3 | 3/3 |
| Real write error: recover and finish files | 3/3 | 3/3 | 3/3 | 3/3 |
| Distinct contracts per repetition | 5/6 | 5/6 | 6/6 | 5/6 |

The improvement comes from one scoped completion reminder after confirmed native
file edits in managed Bot Chats when the agent has not authored a checklist.
It checks the original request against actual work and allows missing authorized
work within the existing iteration allowance. The fixture supplies a missing-file
write only if the runtime continues; this demonstrates runtime recovery, not a
real model's ability to choose the correct continuation. The result metadata
says review requested and `completion_verified: false`.

| Ordinary model requests per execution | Original/previous Hermes | Updated Hermes | OpenBot/Pi |
|---|---:|---:|---:|
| Already complete | 3 | 4 | 3 |
| Premature final | 2 | 4 | 2 |
| Blocked / cancelled | 1 / 1 | 1 / 1 | 1 / 1 |
| Status only | 2 | 2 | 2 |
| Write-error recovery | 4 | 5 | 4 |

The already-complete case pays one extra request. The missing-file case pays two
extra requests and completes the second file. Write-error recovery pays one extra
review. All repeats have these counts. Ordinary chats, disabled configuration,
read-only turns, next-turn reset, stable message/schema prefixes and budget exit
are covered by separate actual-agent tests, including two other authored output
sets (JSON/CSV and Markdown/TSV/JSON). They are not a blinded holdout.

The separate first-settlement race runs two real processes at a controlled
filesystem publication boundary. A second writer resumes only after the first
reply has been observed. Previous Hermes preserves that reply in 0/20 trials;
updated Hermes preserves it in 20/20 (ten answer-first and ten error-first trials
per arm). These forced races are not estimates of incident frequency. A complete
private candidate is atomically linked without replacing an existing final reply;
failed staging/publication cannot reserve an empty reply. No OpenBot score,
power-loss guarantee or exactly-once external-action guarantee is inferred.

The canonical broader selection passes 3,672 tests across 361 files, zero failed,
50 platform skips and no retries on macOS ARM64. All 13 blocking source checks
pass. Linux-only desktop resource gating was correctly marked after the same
failure reproduced on the unchanged previous source on macOS. Native platform
and actual model-task runs are reported separately; these scripted figures do
not replace them or establish overall agent superiority.

## Reproduction and complete receipts

In addition to the runtime packages listed in the main README, the full backend
import graph used exact versions of `@agentclientprotocol/sdk` 1.9.0,
`@anthropic-ai/claude-agent-sdk` 0.3.309, `@muse-code/sdk` 1.4.12, `tldts` 7.4.19,
`jose` 6.2.13, `@noble/hashes` 2.4.0 and `ws` 8.22.0. Package install scripts were
disabled. Bun 1.4.4 and Pi 1.1.0 match OpenBot's native runtime lock. Dependency
and workspace links live outside the Hermes repository.

Use the prepared Hermes test Python with `run_openbot_native.py`,
`task_backend.py`, `run_bot_mode_cycle.py`, `run_original_baseline.py` and
`run_relay_settlement.py`; each exposes required external paths with `--help`.
The real-model protocol is separate: [MODEL_TASKS.md](MODEL_TASKS.md).

All receipts include plans and admissions. Private host paths are replaced;
request/message hashes still identify the originally observed wire data.

| Receipt | Uncompressed SHA-256 |
|---|---|
| [Upstream native scripts](results/openbot-native-backend.json.gz) | `c52ebe71e53e4f3ed503768a300ab1da44cab21dff82e297a6599e24e25280dc` |
| [Initial matched failure](results/native-artifact-baseline.json.gz) | `155659d14a9acdd69f63a3bd248db8a533e20814b626789e65718a7011ec6daa` |
| [Previous/updated/OpenBot Bot Chat cycle](results/bot-mode-cycle.json.gz) | `8f108897dcb9668d072ae742736a097fc822d8a5d3e61ad52d01f300807f500d` |
| [Untouched original Hermes](results/hermes-original-cycle.json.gz) | `8c3e8dced2952d99c324456c766c5b52a0e9a7a39756839d2e8769e2f0fad8f1` |
| [Concurrent reply stability](results/bot-reply-settlement.json.gz) | `a660ff4a97228571c52d7991d1e5d73c0ac3d8e838d7d72c75bbccc7b48c1d0a` |
| [Setup/red regressions/final validation](results/backend-setup-and-validation.json.gz) | `93156c1832642fbcfa8d33c8ca6427ee3d41ef5a6ca253184b68ce47877ba7fa` |

## Native platform validation

The targeted workflow uses standard native GitHub-hosted runners and the locked
PM Python/test environment, not a mocked OS. On source `b315888d`, all 18 selected
bot-related files pass without retries:

| Native platform | Passed | Failed/errors | Platform skips |
|---|---:|---:|---:|
| Ubuntu | 226 | 0 | 2 |
| macOS 15 | 222 | 0 | 6 |
| Windows | 223 | 0 | 5 |

The first Windows run exposed an unchanged relay test's slash-format string
comparison and memory-test IDs exceeding Windows's environment-variable limit.
The correction compares the actual path and assigns short explicit parameter IDs;
the original memory payloads and behavioral assertions remain intact. The first
failure logs are retained. The new reply-settlement and completion-review tests
already passed in that first Windows run. This is native coverage of the selected
contracts, not certification of the entire desktop application or full suite.

[Passing native run](https://github.com/itsflownium/hermes-agent/actions/runs/40467867796),
[first run including Windows failures](https://github.com/itsflownium/hermes-agent/actions/runs/40466619168),
[complete logs](results/bot-platforms.json.gz). Uncompressed receipt SHA-256:
`fb33feaf3f5cc527e4b07c8101bbb60c75dd22dd6e3f33df66c49c44d399d1de`.
