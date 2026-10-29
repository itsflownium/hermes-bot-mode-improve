# Bot quality before/after protocol

This separate protocol compares the imported Hermes runtime with the updated
runtime on two authored, unblinded tasks, twice per task and arm by default.
The repetition count can be set to one before inference when the remaining
budget requires a smaller sample. Every launch is declared before inference
and shuffled with seed 20261029. There
is no best-of selection, automatic rerun, or OpenBot run in this protocol.
The older six-task oracles and their published scores are unchanged.

The cases cover signed-value reconciliation with duplicate rows and four
deliverables, and correction of unsupported persistence/delivery claims in a
long existing document using explicit source facts. JSON types, CSV headers,
source preservation and cross-file totals are checked independently. Raw notes
and final replies remain available for a separate unblinded semantic review;
file-contract success does not certify every explanatory sentence.

Both arms use actual managed Hermes Bot Chat, the same requested Nous Portal
DeepSeek V4.1 Flash model, temperature zero, reasoning requested disabled,
2048 maximum output tokens per request, 16 forwarded requests per launch and
a 150-second turn budget. File and todo tools are enabled; network, installation
and delegation are forbidden in the task. Profiles and workspaces are temporary.
No installed personal Hermes process is used.

The shared persistent spending ledger must already declare the authority passed
to the controller. Previous reservations are never refunded. A protocol cannot
silently increase the declared authority; the default remains $5. This session's
explicitly approved extension is $6 total, shared with all earlier runs. Budget
or transport failures remain in the receipts and are not counted as successes.

Run with the prepared test interpreter after committing source and the protocol:

```sh
python evals/bot_system_benchmark/run_quality_tasks.py \
  --before /path/to/imported-runtime --after /path/to/updated-runtime \
  --budget-ledger /private/path/to/existing-ledger.json \
  --authorized-cap 6.00 --reservation-ceiling 5.44 --repetitions 1 \
  --output /new/receipt-directory
```

The controller requires POSIX process-group cleanup. Its task contracts and
grading regressions run in the native Linux, macOS and Windows reliability
workflow. No inference takes place in CI. A sample this small cannot establish
general reasoning superiority or a new overall comparison against OpenBot.

## Recorded sample: 2026-10-29

The run fixed one repetition per case before inference: four launches in the
seeded order, with baseline `40a67099` and candidate `944991c3`. Both used the
same Nous Portal DeepSeek V4.1 Flash model and the actual managed Bot Chat
agent core in disposable workspaces. No desktop UI or OpenBot run is part of
this sample. Later file-snapshot changes have not received another paid sample.

| Case | Baseline runtime + file contract | Candidate runtime + file contract |
|---|---|---|
| Orders reconciliation | Passed | Passed |
| Capability notes | Passed | Incomplete / failed |
| Total | 2/2 | 1/2 |

All four launches passed the narrow typed-artifact checks. Those checks are
insufficient for the prose requirement: unblinded inspection found that the
candidate capability notes ended in truncated background text without the
requested limits explanation. Its runtime did not complete. The two completed
orders explanations agreed with the source rows and signed 2400-cent sum;
the baseline notes explained the four supplied limits. This is manual review,
not a blinded or independently scored quality benchmark.

The last launch was refused by the **local evaluation reservation ceiling**
of $5.44 within the approved $6 total budget. It was not an upstream rate limit,
although the agent's generic error wording calls it rate limiting. Conservative
shared reservations ended at $5.4313354840. Reservations are not an invoice.
The four launches used 29 forwarded requests; the refused request remains
visible in the worker output. No replacement attempt or best-run selection was
performed. This result does not establish a quality improvement.

[Complete sanitized sample receipts](results/quality-before-after.json.gz)
retain every launch, final response, saved artifact and forwarded request for
this phase. Local paths are replaced and model reasoning fields removed;
original byte hashes remain labelled as such. The uncompressed publication
SHA-256 is `f7010d56ca298b4d85e03c871f4f56332bbad226015ba58bcc0f51c91222a401`.
