/** Run the actual OpenBot discovery function with a shared synthetic catalog. */

import { readFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { performance } from "node:perf_hooks";
import { pathToFileURL } from "node:url";

interface FixtureEntry {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

interface BenchmarkRequest {
  repository_path: string;
  catalog: FixtureEntry[];
  queries: string[];
  limit?: number;
  warmups?: number;
  repetitions?: number;
}

interface RankedResult {
  names: string[];
  schema_names: string[];
  schemas: Record<string, Record<string, unknown>>;
}

async function main(): Promise<void> {
  const request: BenchmarkRequest = JSON.parse(readFileSync(0, "utf8"));
  const repository = resolve(request.repository_path);
  const source = pathToFileURL(join(repository, "src/backend/agent/tool-catalog.ts")).href;
  const { BUILTIN_TOOL_CATALOG, discoverTools } = await import(source);
  const limit = request.limit ?? 5;
  if (!Number.isInteger(limit) || limit < 1 || limit > 10) {
    throw new Error("the shared discovery limit must be between 1 and 10");
  }
  const warmups = Math.max(0, Math.trunc(request.warmups ?? 2));
  const repetitions = Math.max(1, Math.trunc(request.repetitions ?? 10));
  const original = BUILTIN_TOOL_CATALOG.slice();
  const buildStarted = performance.now();
  const catalog = request.catalog.map((entry) => {
    const separator = entry.name.lastIndexOf(".");
    return {
      namespace: separator < 0 ? "benchmark" : entry.name.slice(0, separator),
      tool: separator < 0 ? entry.name : entry.name.slice(separator + 1),
      name: entry.name,
      description: entry.description,
      inputSchema: entry.parameters,
    };
  });
  // This exported mutable array is the injection seam. Ranking, schema selection,
  // query validation and guidance still run in the unchanged production function.
  BUILTIN_TOOL_CATALOG.splice(0, BUILTIN_TOOL_CATALOG.length, ...catalog);
  const catalogBuildMs = performance.now() - buildStarted;

  try {
    const search = (query: string) => {
      const result = discoverTools(
        { namespace: "openbot", tool: "tool_search", arguments: { query, limit } },
        { id: "benchmark-agent", name: "Benchmark", computerUse: false },
      );
      const schemas = Object.fromEntries(result.tools
        .filter((entry: { inputSchema?: unknown }) => entry.inputSchema !== undefined)
        .map((entry: { name: string; inputSchema: Record<string, unknown> }) => [entry.name, entry.inputSchema]));
      return {
        names: result.tools.map((entry: { name: string }) => entry.name),
        schema_names: Object.keys(schemas),
        schemas,
      };
    };
    const results = request.queries.map((query) => {
      if (typeof query !== "string" || query.length < 1 || query.length > 200) {
        throw new Error("queries must contain strings of 1 to 200 characters");
      }
      for (let index = 0; index < warmups; index += 1) search(query);
      const latencies: number[] = [];
      let ranked: RankedResult = { names: [], schema_names: [], schemas: {} };
      for (let index = 0; index < repetitions; index += 1) {
        const started = performance.now();
        ranked = search(query);
        latencies.push(performance.now() - started);
      }
      return { query, ...ranked, latencies_ms: latencies };
    });
    process.stdout.write(`${JSON.stringify({
      implementation: "openbot",
      repository_path: repository,
      seam: "shared synthetic entries replace exported BUILTIN_TOOL_CATALOG data; discoverTools is unchanged",
      timing_boundary: "production discovery ranking, validation, schema selection/guidance and neutral schema extraction; JSON report serialization excluded",
      catalog_build_ms: catalogBuildMs,
      catalog_size: catalog.length,
      results,
    })}\n`);
  } finally {
    BUILTIN_TOOL_CATALOG.splice(0, BUILTIN_TOOL_CATALOG.length, ...original);
  }
}

void main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
