/** Offline queue-store adapter. Production code is imported from --source, never vendored. */
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { homedir, tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { pathToFileURL } from "node:url";

interface QueueItem {
  id: string;
  recipient: string;
  text: string;
  status: string;
}
interface DeliveryContext {
  delivery: { id: string; recipientAgentId: string; status: string; text: string };
}
interface Receipt { messageId: string; deliveries: Array<{ id: string; recipientAgentId: string; status: string }> }
interface MailboxPort {
  initialize(): unknown;
  enqueue(input: object): unknown;
  nextQueued(recipient: string): DeliveryContext | null;
  queuedDeliveryIds(recipient: string): string[];
  getDelivery(id: string): DeliveryContext | null;
  markStarting(id: string): unknown;
  markRunning(id: string, turn: string): unknown;
  markTerminal(id: string, status: string): unknown;
  recoverAsInterrupted(id: string, reason: string): unknown;
  cancel(recipient: string, id: string): unknown;
}
interface DatabasePort { close(): void }
interface ProductionModules {
  MailboxStore: new (path: string, shared: string, db: DatabasePort) => MailboxPort;
  OpenBotDatabase: new (path: string) => DatabasePort;
  run<T>(operation: unknown): Promise<T>;
}
interface CaseResult {
  id: string;
  status: "pass" | "fail" | "runtime_error" | "unsupported";
  expected: string;
  observed: object;
  duration_ms: number;
}

class OpenBotQueue {
  db: DatabasePort | null = null;
  mailbox!: MailboxPort;
  turn = 0;
  constructor(readonly root: string, readonly modules: ProductionModules) {}
  async open() {
    this.db = new this.modules.OpenBotDatabase(this.root);
    this.mailbox = new this.modules.MailboxStore(this.root, join(this.root, "shared"), this.db);
    await this.modules.run(this.mailbox.initialize());
  }
  close() { this.db?.close(); this.db = null; }
  async reopen() { this.close(); await this.open(); }
  async submit(text: string, token: string, recipient = "recipient-a"): Promise<QueueItem> {
    const receipt = await this.modules.run<Receipt>(this.mailbox.enqueue({
      sender: { kind: "user" }, recipientAgentIds: [recipient], text, replyToMessageId: null,
      idempotencyKey: token,
    }));
    return this.get({ id: receipt.deliveries[0].id });
  }
  get(item: { id: string }): QueueItem {
    const context = this.mailbox.getDelivery(item.id);
    if (!context) throw new Error("Accepted queue item is missing.");
    return { id: context.delivery.id, recipient: context.delivery.recipientAgentId,
      text: context.delivery.text, status: context.delivery.status };
  }
  async claim(recipient = "recipient-a"): Promise<QueueItem | null> {
    const context = this.mailbox.nextQueued(recipient);
    if (!context) return null;
    await this.modules.run(this.mailbox.markStarting(context.delivery.id));
    await this.modules.run(this.mailbox.markRunning(context.delivery.id, `benchmark-turn-${++this.turn}`));
    return this.get(context.delivery);
  }
  async finish(item: QueueItem, status = "completed") {
    await this.modules.run(this.mailbox.markTerminal(item.id, status));
  }
  async cancel(item: QueueItem) {
    await this.modules.run(this.mailbox.cancel(item.recipient, item.id));
  }
  async executeQueued(recipient = "recipient-a") {
    const texts: string[] = [];
    for (let budget = 0; budget < 64; budget++) {
      const item = await this.claim(recipient);
      if (!item) break;
      texts.push(item.text);
      await this.finish(item);
    }
    return texts;
  }
}

function same(left: unknown, right: unknown) { return JSON.stringify(left) === JSON.stringify(right); }

async function queueFifo(queue: OpenBotQueue) {
  const expected = Array.from({ length: 4 }, (_, index) => `work-${index}`);
  for (const text of expected) await queue.submit(text, text);
  const executed = await queue.executeQueued();
  return { passed: same(executed, expected), observed: { expected_order: expected, executed_order: executed } };
}

async function queuedCancelSurvivesReopen(queue: OpenBotQueue) {
  await queue.submit("keep-first", "first");
  const cancelled = await queue.submit("cancel-me", "cancel");
  await queue.submit("keep-last", "last");
  await queue.cancel(cancelled);
  await queue.reopen();
  const saved = queue.get(cancelled);
  const executed = await queue.executeQueued();
  return { passed: saved.status === "cancelled" && same(executed, ["keep-first", "keep-last"]),
    observed: { cancelled_status: saved.status, executed } };
}

async function activeCancelRefused(queue: OpenBotQueue) {
  await queue.submit("running-work", "running");
  const active = await queue.claim();
  if (!active) throw new Error("Accepted active fixture was not claimable.");
  let refusal: object | null = null;
  try { await queue.cancel(active); }
  catch (error) {
    if (error instanceof TypeError || error instanceof ReferenceError || error instanceof SyntaxError) throw error;
    refusal = safeError(error, "", queue.root);
  }
  const afterCancel = queue.get(active);
  await queue.finish(active, "interrupted");
  await queue.finish(active, "completed");
  const final = queue.get(active);
  return { passed: refusal !== null && afterCancel.status === "running" && final.status === "interrupted",
    observed: { queued_cancel_refusal: refusal, status_after_refusal: afterCancel.status, final_status: final.status,
      late_completion: "terminal state observed after attempted completion",
      boundary: "queue-store cancellation and terminal-state fencing; no provider interrupt" } };
}

async function restartQueuedRetained(queue: OpenBotQueue) {
  const originalIds: string[] = [];
  for (let index = 0; index < 3; index++) originalIds.push((await queue.submit(`persist-${index}`, `persist-${index}`)).id);
  await queue.reopen();
  const recoveredIds = queue.mailbox.queuedDeliveryIds("recipient-a");
  const executed = await queue.executeQueued();
  return { passed: same(originalIds, recoveredIds) && same(executed, ["persist-0", "persist-1", "persist-2"]),
    observed: { accepted_count: originalIds.length, retained_count: recoveredIds.length,
      identities_preserved: same(originalIds, recoveredIds), executed } };
}

async function activeRestartHonest(queue: OpenBotQueue) {
  await queue.submit("uncertain-work", "uncertain");
  const follower = await queue.submit("follower", "follower");
  const active = await queue.claim();
  if (!active) throw new Error("Accepted active fixture was not claimable.");
  await queue.reopen();
  const persisted = queue.get(active);
  await queue.modules.run(queue.mailbox.recoverAsInterrupted(active.id, "Benchmark restart: provider history unavailable."));
  await queue.finish(active, "completed");
  const recovered = queue.get(active);
  const followerState = queue.get(follower);
  const nextText = queue.mailbox.nextQueued("recipient-a")?.delivery.text ?? null;
  return { passed: persisted.status === "running" && recovered.status === "interrupted" && followerState.status === "queued",
    observed: { persisted_status: persisted.status, recovered_status: recovered.status,
      follower_status: followerState.status, next_claimable_text: nextText,
      recovery_entrypoint: "MailboxStore.recoverAsInterrupted",
      policy: "explicit conservative queue-store recovery; provider-history reconciliation is outside this benchmark" } };
}

async function recipientSeparation(queue: OpenBotQueue) {
  await queue.submit("for-a", "separate-a");
  const other = await queue.submit("for-b", "separate-b", "recipient-b");
  const first = await queue.executeQueued();
  const otherBefore = queue.get(other);
  await queue.reopen();
  const second = await queue.executeQueued("recipient-b");
  return { passed: same(first, ["for-a"]) && otherBefore.status === "queued" && same(second, ["for-b"]),
    observed: { recipient_a_executed: first, recipient_b_before_reopen: otherBefore.status, recipient_b_executed: second } };
}

async function duplicateReplay(queue: OpenBotQueue) {
  const first = await queue.submit("once", "stable-token");
  const retry = await queue.submit("once", "stable-token");
  const executed = await queue.executeQueued();
  await queue.reopen();
  const terminalRetry = await queue.submit("once", "stable-token");
  const oneIdentity = first.id === retry.id && first.id === terminalRetry.id;
  const pending = queue.mailbox.queuedDeliveryIds("recipient-a").length;
  return { passed: oneIdentity && same(executed, ["once"]) && pending === 0,
    observed: { one_identity: oneIdentity, executed, pending_after_terminal_retry: pending,
      terminal_replay_status: terminalRetry.status } };
}

const CASES = [
  ["queue_fifo", queueFifo, "Accepted inputs execute once in admission order."],
  ["queued_cancel_survives_reopen", queuedCancelSurvivesReopen, "Cancelled queued input remains cancelled after reopening."],
  ["active_cancel_refused", activeCancelRefused, "Queued cancellation refuses active work; interrupted terminal state rejects a late completion."],
  ["restart_queued_retained", restartQueuedRetained, "Unstarted accepted inputs keep their identities and order across reopening."],
  ["active_restart_honest", activeRestartHonest, "Uncertain started work is neither replayed nor falsely completed after restart."],
  ["recipient_separation", recipientSeparation, "Draining one recipient leaves another recipient's work intact."],
  ["duplicate_replay", duplicateReplay, "The same idempotency token replays one accepted item before and after completion/reopen."],
] as const;

function safeError(error: unknown, source: string, stateRoot: string) {
  let message = String(error);
  for (const [path, replacement] of [[source, "<source>"], [stateRoot, "<state>"], [homedir(), "<home>"]]) {
    if (path) message = message.split(path).join(replacement);
  }
  return { type: error instanceof Error ? error.name : typeof error, message: message.slice(0, 500) };
}

async function loadModules(source: string): Promise<ProductionModules> {
  const require = createRequire(join(source, "package.json"));
  const { Effect } = await import(pathToFileURL(require.resolve("effect")).href);
  const { MailboxStore } = await import(pathToFileURL(join(source, "src/backend/mailbox-store.ts")).href);
  const { OpenBotDatabase } = await import(pathToFileURL(join(source, "src/backend/openbot-database.ts")).href);
  return { MailboxStore, OpenBotDatabase, run: (operation) => Effect.runPromise(operation) };
}

async function measureCase(id: string, operation: (queue: OpenBotQueue) => Promise<{ passed: boolean; observed: object }>,
  expected: string, root: string, source: string, modules: ProductionModules): Promise<CaseResult> {
  const started = performance.now();
  const queue = new OpenBotQueue(root, modules);
  try {
    await queue.open();
    const result = await operation(queue);
    return { id, status: result.passed ? "pass" : "fail", expected, observed: result.observed,
      duration_ms: Math.round((performance.now() - started) * 1000) / 1000 };
  } catch (error) {
    return { id, status: "runtime_error", expected, observed: safeError(error, source, root),
      duration_ms: Math.round((performance.now() - started) * 1000) / 1000 };
  } finally { queue.close(); }
}

async function main() {
  const index = process.argv.indexOf("--source");
  if (index < 0 || !process.argv[index + 1]) throw new Error("Usage: queue_openbot.ts --source SOURCE");
  const source = resolve(process.argv[index + 1]);
  const root = await mkdtemp(join(tmpdir(), "openbot-queue-component-"));
  let cases: CaseResult[];
  try {
    const modules = await loadModules(source);
    cases = [];
    for (const [id, operation, expected] of CASES) {
      const state = join(root, id);
      await mkdir(state);
      cases.push(await measureCase(id, operation, expected, state, source, modules));
    }
  } catch (error) {
    cases = CASES.map(([id, , expected]) => ({ id, status: "runtime_error", expected,
      observed: safeError(error, source, root), duration_ms: 0 }));
  } finally { await rm(root, { recursive: true, force: true }); }
  console.log(JSON.stringify({ engine: "openbot", source: basename(source), component: "production durable queue store",
    timing_scope: "includes isolated SQLite initialization and case operations; excludes module loading",
    cases, summary: Object.fromEntries(["pass", "fail", "runtime_error", "unsupported"].map(
      (status) => [status, cases.filter((row) => row.status === status).length])) }));
}

void main().catch((error) => {
  const cases = CASES.map(([id, , expected]) => ({ id, status: "runtime_error", expected,
    observed: safeError(error, "", ""), duration_ms: 0 }));
  console.log(JSON.stringify({ engine: "openbot", source: "unavailable", cases,
    summary: { pass: 0, fail: 0, runtime_error: cases.length, unsupported: 0 } }));
  process.exitCode = 1;
});
