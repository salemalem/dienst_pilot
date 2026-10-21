import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { join } from "node:path";

import { API_PORT, API_URL } from "../playwright.config.ts";

const ROOT = join(import.meta.dirname, "../../..");

const DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  "postgresql+psycopg://dienstpilot:dienstpilot@localhost:5433/dienstpilot_e2e";
const REDIS_URL = process.env.E2E_REDIS_URL ?? "redis://localhost:6379/14";
const SEED_DIR = process.env.DIENSTPILOT_SEED_DIR ?? "data/synthetic/v1";

const env = {
  ...process.env,
  DATABASE_URL,
  REDIS_URL,
  DEMO_MODE: "true",
  DIENSTPILOT_SEED_DIR: SEED_DIR,
};

function run(cmd: string, args: string[], cwd = ROOT): void {
  execFileSync(cmd, args, { cwd, env, stdio: "inherit" });
}

async function waitFor(url: string, ms: number): Promise<void> {
  const until = Date.now() + ms;
  for (;;) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      // Not up yet.
    }
    if (Date.now() > until) throw new Error(`${url} did not become ready`);
    await new Promise((r) => setTimeout(r, 500));
  }
}

/**
 * Rebuild the e2e database from the synthetic seed, reset the demo clock (Redis), then start the
 * API and the arq worker (C1 solver runs) against them. Everything here is test infrastructure:
 * the e2e database is separate from the dev stack's.
 */
export default async function globalSetup(): Promise<() => void> {
  run("uv", [
    "run",
    "python",
    "-m",
    "synthdata",
    "generate",
    "--seed",
    "20261020",
    "--out",
    SEED_DIR,
    "--if-changed",
  ]);
  run("uv", ["run", "python", "apps/dashboard/e2e/reset-db.py", DATABASE_URL]);
  run("uv", ["run", "alembic", "upgrade", "head"], join(ROOT, "backend"));
  run("uv", ["run", "python", "-m", "dienstpilot.seeding", SEED_DIR]);
  run("uv", [
    "run",
    "python",
    "-c",
    "import redis,sys; redis.Redis.from_url(sys.argv[1]).flushdb()",
    REDIS_URL,
  ]);

  const children: ChildProcess[] = [];
  const start = (args: string[]): ChildProcess => {
    const c = spawn("uv", ["run", ...args], { cwd: ROOT, env, stdio: "inherit", detached: true });
    children.push(c);
    return c;
  };
  start(["uvicorn", "dienstpilot.main:app", "--port", String(API_PORT)]);
  const worker = start(["arq", "dienstpilot.worker.WorkerSettings"]);
  worker.on("exit", (code) => {
    if (code) console.error(`worker exited with ${String(code)}`);
  });
  await waitFor(`${API_URL}/health/ready`, 60_000);

  return () => {
    for (const c of children) {
      if (c.pid) {
        try {
          process.kill(-c.pid, "SIGTERM");
        } catch {
          // Already gone.
        }
      }
    }
  };
}
