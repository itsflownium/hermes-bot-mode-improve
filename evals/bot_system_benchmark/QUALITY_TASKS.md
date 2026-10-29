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
