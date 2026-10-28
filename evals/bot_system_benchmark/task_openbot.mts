/** Actual OpenBot service, provider driver, SQLite stores and pinned Pi executable. */
import { readFileSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const request = JSON.parse(readFileSync(0, "utf8"));
const root = request.state_directory;
const modelId = request.model_id ?? "scripted";
const selectedModel = `fixture/${modelId}`;
const home = join(root, "home");
const piHome = join(root, "pi-agent");
mkdirSync(home, { recursive: true });
mkdirSync(piHome, { recursive: true });
process.env.HOME = home;
process.env.PI_CODING_AGENT_DIR = piHome;
writeFileSync(join(piHome, "models.json"), JSON.stringify({providers: {fixture: {
  baseUrl: request.base_url, api: "openai-completions", apiKey: "fixture-local-only",
  models: [{id: modelId, name: "Evaluation model", reasoning: false,
    input: ["text"], contextWindow: 128000, maxTokens: request.max_tokens ?? 2048,
    cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
}}}));
writeFileSync(join(piHome, "settings.json"), JSON.stringify({
  defaultProvider: "fixture", defaultModel: modelId, defaultThinkingLevel: "off",
}));
const repository = request.repository;
const load = (relative: string) => import(pathToFileURL(join(repository, relative)).href);
const resolver = createRequire(pathToFileURL(join(repository, "package.json")));
const { Effect } = await import(pathToFileURL(resolver.resolve("effect")).href);
const { AGENT_PROVIDERS } = await import(pathToFileURL(resolver.resolve("@openbot/contracts/ipc")).href);
const { AgentService } = await load("src/backend/agent-service.ts");
const { AgentStore } = await load("src/backend/agent-store.ts");
const { MailboxStore } = await load("src/backend/mailbox-store.ts");
const { OpenBotDatabase } = await load("src/backend/openbot-database.ts");
const { runCauseEffect } = await load("src/backend/effect-boundary.ts");
const unavailable = () => Effect.die(new Error("Desktop/browser operation outside this backend fixture"));
const browser = {
  listTabs: () => [], beginTakeover: unavailable, endTakeover: () => {},
  userControlTabFor: () => null, awaitUserControlRelease: unavailable,
  resolveUploadTarget: unavailable, handleDynamicTool: unavailable,
  onChanged: () => () => {}, onControlChanged: () => () => {}, onDocumentChanged: () => () => {},
  clearControls: () => {}, endControl: () => {}, close: () => Effect.void,
  clearAgentSession: () => Effect.void,
};
const database = new OpenBotDatabase(join(root, "user-data"));
const store = new AgentStore(join(root, "user-data"), home, database);
const mailbox = new MailboxStore(join(root, "user-data"), store.sharedRoot, database);
const agents = new AgentService({
  store, mailbox, browser, preferredProvider: "pi", preferredModel: selectedModel,
  offProviders: AGENT_PROVIDERS.filter((provider: string) => provider !== "pi"),
  bundledExecutables: {claude: null, grok: null, pi: request.pi_executable},
  requestTimeoutMs: request.request_timeout_ms ?? 20000,
});
const events: any[] = [];
agents.on("event", (event: any) => events.push(event));
let completionTimer: ReturnType<typeof setTimeout> | undefined;
try {
  await runCauseEffect(agents.initialize());
  let agentId: string | null = null;
  const expectTurn = () => new Promise<any>((resolve, reject) => {
    completionTimer = setTimeout(() => {agents.off("event", listen); reject(new Error("No terminal backend event within evaluation deadline"));}, request.turn_timeout_ms ?? 45000);
    const listen = (event: any) => {
      if (event.type !== "turn-completed" || event.agentId !== agentId) return;
      clearTimeout(completionTimer);
      agents.off("event", listen);
      resolve(event);
    };
    agents.on("event", listen);
  });
  const completion = expectTurn();
  completion.catch(() => {});
  const agent = await runCauseEffect(agents.createAgent({
    name: "Backend fixture", description: "Local deterministic artifact test",
    avatarSeed: "backend-fixture", avatarHue: null, initialMessage: request.prompts?.[0] ?? request.prompt,
    provider: "pi", model: selectedModel,
  }, (created: any) => Effect.sync(() => {
    agentId = created.id;
    if (request.seed_status_file) writeFileSync(join(created.workspacePath, "report.txt"), "ORIGINAL");
    for (const [name, content] of Object.entries(request.fixture_files ?? {})) {
      writeFileSync(join(created.workspacePath, name), content as string);
    }
    return created;
  })));
  const terminal = await completion;
  const terminals = [terminal];
  for (const prompt of (request.prompts ?? []).slice(1)) {
    const next = expectTurn();
    next.catch(() => {});
    await runCauseEffect(agents.sendMessage({agentId: agent.id, text: prompt}));
    terminals.push(await next);
  }
  const conversation = await runCauseEffect(agents.readConversation(agent.id));
  const outputs = Object.fromEntries(["report.txt", "attachment.txt"].map(name => {
    const path = join(agent.workspacePath, name);
    return [name, existsSync(path) ? readFileSync(path, "utf8") : null];
  }));
  process.stdout.write("OPENBOT_TASK_RESULT=" + JSON.stringify({
    outputs, terminal, terminals, provider: agent.provider, model: agent.model,
    ...(request.return_workspace ? {workspace_path: agent.workspacePath} : {}),
    messages: conversation.messages, queue: agents.listQueue(agent.id),
    events: events.map(({type, code, status, turnId}: any) => ({type, code, status, turnId})),
    execution: "real AgentService + real PiAgentClient + pinned Pi native tool loop",
  }) + "\n");
} finally {
  clearTimeout(completionTimer);
  await runCauseEffect(agents.stop());
  database.close();
}
