# Completion and recovery fault contracts

This protocol compares the previous draft, `789ac877`, with the completion and
recovery changes. It is separate from the OpenBot discovery/queue comparison and
does not provide an OpenBot task-completion score or an overall agent ranking.

The fixtures are written by the contributor, small, targeted, and unblinded.
Scripted responses deliberately exercise failure paths; this is not a measurement
of a real model's ability or probability of solving normal user tasks.

## Fixed cases and acceptance criteria

| Case | Actual execution and acceptance check |
|---|---|
| Premature final | Real AIAgent, HTTP client and file tools; both requested files must contain their exact specified bytes before the next user turn. The provider deliberately returns an early final, with a fixed continuation available. |
| Already complete | Both files have exact contents; a satisfied checklist adds no continuation. |
| Blocked | The response explains missing user input; no output files are fabricated. |
| Cancelled | Both items are cancelled at the user's request; exactly two ordinary requests, no continuation. |
| Historical list | A status-only turn with old pending work takes one request and performs no writes. |
| Exhausted budget | Two allowed iterations, no files produced; the final explicitly reports unfinished work and unverified completion. |
| Invalid MCP reply | An owned stdio server commits a SQLite row, then returns malformed MCP content; the real SDK and production handler must report unknown outcome plus required reconciliation, with exactly one committed effect. |
| Successful MCP reply | Same server returns valid content; exactly one effect, success, no uncertainty flag. |

Every completion case also checks that previously sent message rows stay byte
equivalent in later requests, and tool schemas stay unchanged. The premature-final
case resumes for a status-only user turn to check reset behavior. Deferred
`todo_list` is invoked through the advertised `tool_call` bridge in both arms.
Artifact acceptance is captured before the resumed turn.

Run three fresh subprocess repetitions per case and arm, in a fixed shuffled
order (seed `20261027`), with a 45-second deadline per launch. Keep failed cases,
exceptions and deadlines in the receipt; no file retry or best-of selection.
The runner verifies every tracked baseline blob against the old Git commit
(normalizing the declared PowerShell CRLF exports back to Git's LF storage) and
requires a clean measured after tree. Added harness/test files in the baseline
archive do not change its production implementation. No inference is paid for.

```sh
python evals/bot_system_benchmark/run_task_recovery.py \
  --before /path/to/unchanged-789ac877-archive \
  --after /path/to/clean-measured-checkout \
  --output /path/to/raw-receipts.json
```

Additional canonical regression probes inject timeout, interruption, invalid
reply, and an OAuth recovery followed by a committed write and lost reply. They
use a real SQLite effect oracle and a controlled in-process RPC boundary.
Read-only timeouts, pre-dispatch failures, successful replies and application
errors are negative controls. Shared-budget tests use atomic reservations across
ten ordinary threads, real child construction with a constructor double, local
caps, owned refunds, an inherited old pool and a fresh root-turn pool. These do
not run model subagents or measure task quality/cost savings.

## Scope of the changes

The default completion continuation is bounded to one per turn and never grants
permission or extends the iteration allowance. Checklist status is a self-report,
not an acceptance oracle. A model can still mark a task complete incorrectly.
Unknown MCP outcomes require inspecting external state; the change provides no
exactly-once ledger or cross-process crash recovery. Existing annotated read-only
retry and pre-dispatch OAuth recovery semantics are retained. The optional shared
iteration pool is not a cap on physical model attempts, paid tools or dollars.

## Recorded results

Before: `789ac8778cc5c82d391dae8ffc9d2b44b86388a4`. After: `e748982b0e5248d5873279d6d89870aff77205a0`.
The runner verified all **21,463 tracked baseline contents**,
with the declared PowerShell line-ending normalization, and started with a clean
after tree. All **48/48 planned subprocesses completed**, with no worker errors,
no deadlines and no omitted cases. Platform: Darwin arm64,
Python 3.14.9.

| Fixed contract, three fresh-process repetitions | Previous draft | Updated Hermes |
|---|---:|---:|
| Premature final: both output files correct | 0/3 | 3/3 |
| Already complete: no extra continuation | 3/3 | 3/3 |
| Missing input: honest blocker, no fabricated files | 3/3 | 3/3 |
| Cancelled work: no continuation | 3/3 | 3/3 |
| Historical status query: no write or continuation | 3/3 | 3/3 |
| Budget exhausted: unfinished work reported | 0/3 | 3/3 |
| Committed MCP write / invalid reply: outcome unknown | 0/3 | 3/3 |
| Successful MCP write: one effect, normal success | 3/3 | 3/3 |

Completion has six distinct contracts: **4/6 before, 6/6 after** in each
repetition (12/18 and 18/18 executions). Two cases grade completed output
files: **1/2 before, 2/2 after** in each repetition. The other four cases test
honest stopping and boundaries. Repetition checks reproducibility; these are not
independent natural-task samples or a statistically estimated general success rate.

The local MCP server committed exactly one effect in **all six executions per
arm**. Neither version automatically replayed the measured write. The improvement
is an explicit unknown outcome and reconciliation requirement after an invalid
reply, not a newly demonstrated reduction in duplicates. Both retain normal
success on valid replies. The blocked completion case takes two ordinary requests
before and three after; the reminder adds a request even when work is blocked. All completion launches retained the sent message
prefix and tool schemas, including the resumed status-only conversation.

The broader canonical selection passed **3,203 tests, 0 failures, 15 platform
skips across 308 files**, with `HERMES_TEST_FILE_RETRIES=0`. An earlier expanded
run exposed 24 failures because the new uncertainty message hid original MCP
validation details; those diagnostics were preserved and the same selection
rerun successfully. A focused selection also passed 53/53 checks. All 13 blocking
repository checks passed on the implementation commit. The full repository suite,
native Windows/Linux runs, provider crashes and an OpenBot model/task comparison
were not run. Existing separately documented upstream shell-wrapper failures are
outside this selection.

[Complete raw receipts](results/task-recovery.json.gz), including the before
arm's failing contracts, diagnostics and every scheduled launch. Uncompressed
SHA-256: `de5ebce49704363e5516098413da44932ff78c616b2f7d16ce83a4ab20098ed4`.

The previous OpenBot search/queue and live MCP comparisons remain in
[SCORECARD.md](SCORECARD.md) and [ONLINE.md](ONLINE.md); their pinned revisions
and boundaries are unchanged. There is no combined overall bot score.
