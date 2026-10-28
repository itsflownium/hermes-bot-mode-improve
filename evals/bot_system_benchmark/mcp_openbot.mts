/** Read-only live MCP discovery through OpenBot's actual backend probe. */
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";
import { createRequire } from "node:module";

const request = JSON.parse(readFileSync(0, "utf8"));
const fromOpenBot = createRequire(pathToFileURL(`${request.repository}/package.json`));
const { Effect } = await import(pathToFileURL(fromOpenBot.resolve("effect")).href);
const { inspectMcpServer } = await import(pathToFileURL(`${request.repository}/src/backend/mcp-probe.ts`).href);
const config = {
  id: "public-network-check", name: "public-network-check", enabled: true,
  transport: "http", command: "", args: [], env: [], envPassthrough: [],
  workingDirectory: "", url: request.url, headers: [],
};
const started = performance.now();
try {
  const result = await Effect.runPromise(inspectMcpServer(config, request.timeout_seconds * 1000));
  process.stdout.write(JSON.stringify({
    phase: "connect_and_discover", tool_names: result.tools,
    tool_count: result.toolCount, error: result.error,
    elapsed_ms: performance.now() - started,
  }) + "\n");
} catch (error) {
  process.stdout.write(JSON.stringify({
    phase: "connect_and_discover", tool_names: [], tool_count: 0,
    error: {class: error instanceof Error ? error.name : "Error", message: String(error).slice(0, 1000)},
    elapsed_ms: performance.now() - started,
  }) + "\n");
}
