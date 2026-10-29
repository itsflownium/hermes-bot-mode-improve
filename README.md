# Hermes Bot Mode Improvements

Custom improvements to **[Hermes Agent](https://github.com/NousResearch/hermes-agent)'s Bot Mode**, focused on reliable task completion, recovery, bot messaging and verifiable outputs.

This repository contains the full Hermes source with the Bot Mode changes included on `main`. Hermes Agent and its original Bot Mode are built by **Nous Research**; this fork documents the additional improvements and their measured results.

[What changed](#what-changed) · [Watch the demo](#demo) · [Verified results](#verified-results) · [Use this version](#use-this-version)

## What changed

| Area | Improvement |
|---|---|
| Task completion | Bounded continuation and review help bots check requested deliverables before finishing, while respecting the existing iteration and permission limits. |
| Answer review | Review receives head/tail excerpts from up to six changed files, covers completed checklists, and checks explanations, calculations and unsupported guarantees. |
| Windows file handling | Drive-letter and directory-junction aliases share file evidence. Content snapshots detect changes while comparing timestamp observations consistently. |
| Patching | LF/CRLF-equivalent anchors match precisely before approximate strategies, preventing edits from selecting a similar neighboring line. |
| Bot messaging | Synchronous and asynchronous waiters use the receipt writer's lock, avoiding interrupted reads during publication. |
| Recovery | Uncertain MCP write outcomes retain their original diagnostics and require reconciliation rather than assuming success or blindly repeating an action. |
| Reproducibility | Fixed native test selections, complete receipts and retained failed runs make the results inspectable. Explicit empty selections cannot accidentally start the whole test suite. |

See the [implementation overview](BOT_MODE_IMPROVEMENTS.md), [completion and recovery contracts](evals/bot_system_benchmark/TASK_RECOVERY.md), and [Windows and answer-review details](evals/bot_system_benchmark/RELIABILITY_UPDATE.md).

## Demo

[![Watch the modern Hermes and OpenBot demo](assets/demos/hermes-openbot-modern-demo.png)](assets/demos/hermes-openbot-modern-demo.mp4)

**[Watch or download the modern demo](assets/demos/hermes-openbot-modern-demo.mp4)** · [Capture evidence and provenance](assets/demos/README.md)

The 39.6-second silent edit uses genuine native Hermes and OpenBot screenshots. It shows Hermes `40a67099` and OpenBot 0.52.1, before the latest Windows fixes. It is an edited walkthrough; screen-display durations are editorial. Both applications passed the captured task's three file checks. Model routes and fallback handling differed and are disclosed in the evidence.

## Verified results

The [completed native validation run](https://github.com/itsflownium/hermes-bot-mode-improve/actions/runs/40810618172) tested runtime revision `96a9276d` across a fixed **43-file selection**, with file retries disabled:

| Native host | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Windows | **582** | **0** | 25 |
| Linux | **598** | **0** | 9 |
| macOS | **587** | **0** | 20 |

Three additional focused Windows repetitions each passed **19 tests with zero failures** and two host skips. All **13 local blocking source checks** passed. Host markers explain the different skip counts; these selections do not certify the full test suite or general model quality.

[Full logs and earlier failures](evals/bot_system_benchmark/RELIABILITY_UPDATE.md#final-expanded-validation) · [Machine-readable summary and hashes](evals/bot_system_benchmark/results/reliability-validation.json)

### Hermes and OpenBot evaluations

The [historical six-task terminal sample](evals/bot_system_benchmark/MODEL_TASKS.md#oracle-correction-and-completed-terminal-follow-up) recorded **Hermes 6/6 and OpenBot 5/6**, with a separate before-Hermes recovery control of 0/1. Those authored cases and revisions predate this follow-up and do not establish an overall product ranking.

The [new two-case before/after Hermes model sample](evals/bot_system_benchmark/QUALITY_TASKS.md#recorded-sample-2026-10-29) completed **2/2 on the baseline and 1/2 on the candidate**. The last candidate attempt hit the local evaluation spending guard and left its prose incomplete. Every attempt is retained; this small, unblinded sample does not demonstrate a quality improvement.

[All comparison protocols and receipts](evals/bot_system_benchmark/README.md) cover tool discovery, queues, recovery, native backend tasks and model-driven tasks, with their individual measurement boundaries.

## Use this version

Clone this repository to use the improved source:

```bash
git clone https://github.com/itsflownium/hermes-bot-mode-improve.git
cd hermes-bot-mode-improve
```

Follow the [source checkout development setup](CONTRIBUTING.md#development-setup) to build this version. The [Bot Mode user guide](website/docs/user-guide/bot-mode.md) explains the bot roster, profiles, routines and chats.

The unchanged original project introduction and general installation guidance are preserved in [README.upstream.md](README.upstream.md). Its upstream installer targets the original Hermes distribution; use this checkout's setup for the improvements in this repository.

## Upstream and license

Based on **[Hermes Agent by Nous Research](https://github.com/NousResearch/hermes-agent)**. Original attribution and the [MIT license](LICENSE) are preserved. This is a community improvement fork for Hermes Agent's Bot Mode.
