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

## Answer review

The new regression file fails all four cases against the imported runtime.
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

An explicit empty `--files` value previously fell back to default discovery.
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
