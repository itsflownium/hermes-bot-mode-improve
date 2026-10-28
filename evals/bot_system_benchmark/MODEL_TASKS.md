# Actual model task protocol

Use the user's authorized DeepSeek V4.1 Flash model (`deepseek/deepseek-v4.1-flash`)
through Nous Portal for original Hermes `c714c424`, updated Hermes and unchanged
OpenBot `f91535fb` with its real AgentService/Pi runtime. The total authorized model
spending cap is $5, shared across attempts. No separate provider account is used.

`model_tasks.py` fixes the prompts, input files and acceptance checks before runs:

| Task | Required outcome |
|---|---|
| Data summary | Deduplicate paid orders; correct JSON totals and CSV rows; preserve input |
| Config migration | Correct schema migration, preserve unrelated values/original file, migration note |
| Code repair | Independent five-test suite passes, test source unchanged, saved test output |
| Transient recovery | Retry exit 75 exactly once, correct report/status, helper unchanged |
| User correction | Two actual user turns; update 17 to 43 and record the change |
| Missing input | Explain the missing source/columns, no fabricated source/report |

Run six tasks, three variants and two fresh-process repetitions: 36 planned
launches in a fixed shuffle (seed 20261027). Keep every admission, timeout, transport
error and failure. A passing artifact is insufficient if the runtime ends in a
failure. These authored cases are unblinded and small; repeated runs are not
independent estimates of general task success probability.

Both native loops use a local proxy to the same actual Nous model. It sets
temperature 0, requests disabled reasoning, caps each response at 2,048 tokens and buffers
the same upstream nonstreaming response into SSE when required by a native client.
The proxy never scripts model decisions. System prompts, tool schemas and native
tools differ. Every variant has a common cap of 16 model requests per launch
(shared by both turns in the correction task); Hermes also retains its ordinary
16-iteration limit. The existing 150-second per-turn deadline applies to both.
Hermes enables file, terminal and checklist tools in actual managed
Bot Chats, without preloaded checklists. OpenBot runs its native Pi tools. Memory,
project context and delegation are excluded from these task fixtures. Work stays
inside temporary local workspaces; no external task action or package install is
requested. This does not test the desktop UI or every product capability.

The proxy stores no credentials in the task workers. It rejects oversized requests
and disallows other upstream hosts/models. Before each billable request, it reserves
a conservative amount against the shared persistent ledger: UTF-8 body bytes plus
8,192 overhead tokens and the output cap, using doubled current/original advertised
catalog prices. Reservations are never refunded. It stops at $4.50 reserved, leaving
headroom below the $5 authority, or 400 requests. Usage and any returned cost are
retained; advertised-price estimates are not invoices. The same ledger must be used
for any diagnostic/repeated attempts. A budget stop stays visible and does not count
as a passing task.

Capture all output artifacts/hashes, independent check output, native final/queue
states, model responses, usage, model IDs, tool calls/results and request hashes.
Omit authorization headers and production system-prompt text. Retain every failed
task when fixing a real defect. Do not change prompts, grading rules or select a
best attempt to claim a win. Report individual task results and gaps. Elapsed times
include different native setup work and proxy buffering; no product speed ranking
or weighted overall bot score follows.

## Follow-up after the initial 36 launches

The initial run is retained in full: original Hermes passes 11/12 executions,
updated Hermes 10/12 and OpenBot/Pi 8/12. Updated Hermes misses one data-summary
execution (a generated parser uses the display separator instead of the file's
delimiter) and one user-correction execution (wrong structure/values). Original
Hermes misses one correction execution. OpenBot misses one summary, both code
repair executions and one recovery deliverable. Successful code
repair and transient retry are reported separately from omitted output files.

The subsequent improvement clarifies numbered file previews and supplies bounded,
policy-checked current local file excerpts to the existing Bot Chat completion review.
It preserves the per-turn reminder limit, permissions and iteration allowance.
Excerpts are untrusted, possibly partial data, not semantic proof; they cannot
establish whole-file read knowledge for overwrite permission.
Document extraction and remote backends require explicit scoped reads; the reminder
does not start automatic remote I/O. At most three excerpts of 1,600 characters
each fit a shared 6,000-character envelope. A missing active task identity prevents
automatic reads.

`run_model_readback.py` fixes a 16-launch follow-up before inference: repeat all six
unchanged tasks twice on the new source (12 launches), plus one fresh unchanged
before and OpenBot execution for each affected task (four launches). The before
archive is `5bdbd90f`, whose production Python matches the initial `b315888d` model
run. Verify every tracked Python blob; retain the same fixture digest and grading
rules, shared model/settings/ledger, and all earlier failures. Shuffle seed is
20261028. No best-of selection or replacement of the initial results is allowed.
Small samples and nonidentical prompts/tool surfaces still preclude an overall
product ranking. The provider can report reasoning tokens despite the common
requested setting; retain that usage rather than claiming no reasoning occurred.

## Oracle correction and completed-terminal follow-up

The correction prompt in the first two protocols did not explicitly require a
flat root object, although its frozen oracle did. One follow-up answer uses a
nested object with the right corrected values and fails that shape requirement.
Keep the original strict 11/12, 10/12, 8/12 and follow-up counts, but do not use the
ambiguous correction row to rank task quality. Excluding that row, the initial
five-task executions are original Hermes 10/10, updated Hermes 9/10 and OpenBot
6/10. The readback follow-up is 9/10 on those unchanged five tasks. This is not a
retroactive regrade that converts a failure into a product win.

A subsequent named protocol (`--protocol terminal`) supplies an explicit exact
root JSON schema to both products through `PRECISE_CORRECTION`; every other prompt,
input and acceptance rule stays unchanged. Predeclare 13 launches: one fresh
current-Hermes and OpenBot run for each of all six tasks, plus one unchanged
before-Hermes recovery control. The before source is `42489936`; shuffle seed is
20261029. Both products retain the same 16-request per-launch cap, model/settings
and 150-second per-turn limit. Keep all earlier rows and the oracle ambiguity.

The product change covers tasks performed entirely through completed terminal
commands. Their known exit codes can enable the same one-per-turn Bot Chat review;
successful exit alone does not verify requested output files. Other task IDs cannot
enable a turn's review. Text/file-read turns are unchanged; a read-only terminal
command may now incur one review. No command is automatically repeated.

The shared $5 authority and all earlier reservations remain intact. Before this
additional protocol, the internal reservation ceiling increases from $4.50 to
$4.95 and the global request-count guard from 400 to 500. This allows the paired
cases within the user's existing authority; per-task effort does not increase.
The ledger records this extension, never refunds an earlier reservation, and
refuses any configured ceiling above $5. Provider-reported cost remains separate
from conservative reservations and is not an invoice.
