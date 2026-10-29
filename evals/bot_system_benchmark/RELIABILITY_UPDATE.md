# Windows reliability and answer review follow-up

The implementation starts from the exact imported file tree at `6ea5c928`,
equivalent to Hermes source `40a67099`. Importing that tree did not make the
final revision's Windows failures disappear.

## Windows evidence and correction

The [historical final-source run](https://github.com/itsflownium/hermes-agent/actions/runs/40476984272)
passed Linux and macOS, but its current-source Windows selection reported
293 passed, 2 failed and 18 skipped across 23 files. The same job also ran an
unchanged upstream control: those six failures are a separate baseline result,
not six additional failures in the improved source. The older green table in
OPENBOT_BACKEND.md applies specifically to `b315888d`.

A [fresh unchanged-runtime probe](https://github.com/itsflownium/botting-user/actions/runs/40803221220)
passed the two file-tool test files: 65 passed and 13 skipped. It therefore did
not establish that the historical failure was fixed. The follow-up
[native Windows regressions](https://github.com/itsflownium/botting-user/actions/runs/40803788173)
reported 63 passed, 4 failed and 13 skipped: both new drive-letter/junction
alias cases failed, along with two intermittent existing dedup cases.

Windows host paths previously received lexical normalization only. A lowercase
drive or a directory junction could consequently name the same bytes with a
different read-tracking key or full-write baseline. Host paths now resolve to
the canonical filesystem path, as on POSIX. Container paths remain in the remote
POSIX namespace. The new tests run on native Windows; no host OS is simulated.

The broader intermediate run at `60cc2568` then exposed a separate snapshot
failure: Windows reported 340 passed, 24 failed and 22 skipped in 31 files.
Its [complete failure log](results/windows-intermediate-failure.log.gz) is
retained, along with the [earlier alias regression log](results/windows-alias-before.log.gz),
so the private workflow links are not the only available evidence. Linux and
macOS passed that intermediate selection. One Windows failure was an existing
POSIX-only `getuid` test that the broader selection newly included; it now has
a POSIX marker and a separate native Windows scratch-directory contract.

File snapshots previously compared `os.stat` creation/change timestamps
directly with `os.fstat` timestamps. Their Windows semantics can differ after
a rewrite. The shared snapshot helper now requires stability within each API
and matching device/inode, size and last-write time across APIs. Creation/change
time and mode must remain unchanged within each API. Hashes still detect
same-size content changes with restored modification times. The correction
applies to file-tool read/write baselines and verification workspace snapshots.
The workflow records real native file observations and runs three separate
Windows read-contract repetitions with retries disabled; any failure fails
the job, even if another repetition passes.

## Answer review

The new regression file fails all four cases against the imported runtime
([retained baseline output](results/answer-review-before.log.gz)).
It exercises the actual agent and local HTTP provider boundary. Review now
receives bounded head/tail excerpts from up to six changed files and explicitly
reports how many files were omitted. Completing a checklist no longer bypasses
the existing one-per-turn managed Bot Chat review. The review also covers
supporting explanations and final-answer claims, calculations and guarantees.

Excerpts remain untrusted data and cannot authorize a whole-file overwrite.
An explicit full read is still required when the write guard lacks current
whole-file knowledge. Existing permissions, iteration limits, configuration
opt-out and append-only conversation history remain in effect. Better evidence
and guidance are not a guarantee that a model will catch every factual error.

## Test execution and provenance

An explicit empty `--files` value previously fell back to default discovery
([retained baseline output](results/empty-selection-before.log.gz)).
It now remains an empty selection and fails without executing unselected tests.
The regression uses a tiny disposable suite, not the real full suite. Bare
runner invocation still intentionally means full discovery. Optional bytecode
warm-up is serial, avoiding an additional CPU-wide process pool before tests.

The fixed file-backed reliability selection is committed beside the benchmark
and used on native Ubuntu, macOS and Windows with file retries disabled. Results
from `scripts/check` are local blocking source checks; they are distinct from
GitHub check-run conclusions. Full-suite failures must be triaged individually;
the audit's sampled environmental failures do not classify all other failures.

The formerly missing historical terminal-phase receipts are published in
MODEL_TASKS.md, including the before-control and transport failure. The new
QUALITY_TASKS.md protocol is separate and preserves the older task oracles.
The single initial import commit remains intentional; the original improvement
history is preserved in the Hermes draft PR.

## Earlier snapshot validation

At source `96fdd6e2`, the fixed 33-file reliability selection on native macOS
reported **391 passed, 0 failed, 18 skipped** with file retries disabled.
The skipped host-specific cases require their actual CI hosts. All **13 local
blocking source checks** passed with no code-health findings. These are selected
contracts and lint checks, not a full-suite or general answer-quality score.

The [first public native run](https://github.com/itsflownium/hermes-bot-mode-improve/actions/runs/40808850160)
at `96fdd6e2` reported Linux **402 passed, 0 failed, 7 skipped** and macOS
**391 passed, 0 failed, 18 skipped**. Windows reported **383 passed, 2 failed,
24 skipped**; its three read repetitions each reported **42 passed, 1 failed,
10 skipped**. Full [Windows](results/native-windows-96fdd6e2.log.gz),
[Linux](results/native-linux-96fdd6e2.log.gz) and
[macOS](results/native-macos-96fdd6e2.log.gz) logs remain available.

The remaining Windows failures identified two further production defects:

- A bare-LF patch anchor could miss CRLF text and fall through to similarity
  matching, selecting a neighboring line or refusing a valid patch. A precise
  LF/CRLF-equivalent strategy now runs before approximate strategies, preserves
  original offsets and replacement line endings, and retains ambiguity and
  `replace_all` rules. [All three new portable regressions failed before the fix](results/line-ending-before.log.gz).
- Receipt waiters read outside the writer's lock, causing a Windows sharing
  violation during publication. Both synchronous and asynchronous waiters now
  use the existing short locked receipt read; malformed and unreadable committed
  data still fail closed. [Both event-coordinated publication regressions failed before the fix](results/receipt-publication-before.log.gz).

The final manifest expands to 43 files to cover matcher, patch-parser, approval
and mailbox consumers, including real Windows ACL tests. The three Windows
repeatability runs now target deduplication, native file identity, settled
message waits and receipt publication. The complete known-file write-baseline
file remains in the broad selection; the earlier three failures are retained.
Any failed repetition still fails the job, with file retries disabled.

## Final expanded validation

The [completed public native run](https://github.com/itsflownium/hermes-bot-mode-improve/actions/runs/40810618172)
passed every job at runtime source `96a9276d`. All 43 selected files ran with
file retries disabled. Host markers account for different skip counts.

| Native host | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Linux (`ubuntu-latest`) | 598 | 0 | 9 |
| macOS (`macos-15`) | 587 | 0 | 20 |
| Windows (`windows-latest`) | 582 | 0 | 25 |
| Local macOS | 587 | 0 | 20 |

Each of the three focused Windows repetitions passed **19 tests, 0 failed,
2 skipped**. The broad Windows run also passed both actual ACL tests, both
receipt-publication tests, all three line-ending tests and the complete
known-file write-baseline file. The two failures from the first public run
are resolved in this selection. No failed run was replaced or hidden.

All **13 local blocking source checks** passed, with zero code-health findings
across 23 changed Python files. The final video/evidence package also passed
the staged blob-size guard. Publication-only commits add assets, receipts and
documentation after the tested runtime revision; they do not change production
or test code.

Full logs are retained for [Windows](results/native-windows-96a9276d.log.gz),
[Linux](results/native-linux-96a9276d.log.gz),
[macOS](results/native-macos-96a9276d.log.gz),
[local macOS](results/local-macos-96a9276d.log.gz) and
[local source checks](results/source-checks-96a9276d.log.gz).
The [machine-readable summary](results/reliability-validation.json) records
the runtime revision, manifest hash, counts and every archive's uncompressed hash.
These selected contracts do not certify the full suite or general model quality.

The [new real-model sample](QUALITY_TASKS.md#recorded-sample-2026-10-29)
is also retained: baseline 2/2 completed versus candidate 1/2. The last candidate
launch exhausted the local reservation ceiling and left incomplete prose.
Deterministic evidence-review regressions passing does not turn that model
result into a quality win.
