import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { once } from "node:events";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const repositoryRoot = resolve(import.meta.dirname, "..");
const localPython = join(repositoryRoot, ".venv", "bin", "python");
const pythonCommand = existsSync(localPython) ? localPython : "python";
const children = [];
const arguments_ = process.argv.slice(2);
if (
  arguments_.length > 1 ||
  (arguments_.length === 1 && arguments_[0] !== "--auth-timing")
) {
  throw new Error("supported E2E argument: --auth-timing");
}
const authTiming = arguments_[0] === "--auth-timing";

function run(command, args, options = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, args, {
      cwd: repositoryRoot,
      env: options.env ?? process.env,
      stdio: "inherit",
    });
    child.once("error", rejectRun);
    child.once("exit", (code, signal) => {
      if (code === 0) resolveRun();
      else rejectRun(new Error(`${command} exited with ${code ?? signal}`));
    });
  });
}

function start(command, args, env, numericDiagnosticsOnly = false) {
  const child = spawn(command, args, {
    cwd: repositoryRoot,
    env,
    // Diagnostic API startup/background failures must not print tracebacks,
    // SQL parameters or credentials. Readiness/exit failures remain fatal;
    // request failures are reported through the numeric metrics endpoint.
    stdio: numericDiagnosticsOnly ? ["ignore", "ignore", "ignore"] : "inherit",
  });
  children.push(child);
  return child;
}

async function assertCanaryAbsent(path, canary) {
  if (!existsSync(path)) return;
  const entries = await readdir(path, { withFileTypes: true });
  for (const entry of entries) {
    const candidate = join(path, entry.name);
    if (entry.isDirectory()) await assertCanaryAbsent(candidate, canary);
    else if ((await readFile(candidate)).includes(Buffer.from(canary))) {
      throw new Error("Pair Code canary persisted in an E2E artifact");
    }
  }
}

function capture(command, args) {
  return new Promise((resolveCapture, rejectCapture) => {
    const chunks = [];
    const child = spawn(command, args, {
      cwd: repositoryRoot,
      env: process.env,
      stdio: ["ignore", "pipe", "ignore"],
    });
    child.stdout.on("data", (chunk) => chunks.push(chunk));
    child.once("error", rejectCapture);
    child.once("exit", (code) => {
      if (code === 0) resolveCapture(Buffer.concat(chunks));
      else rejectCapture(new Error(`${command} canary scan failed`));
    });
  });
}

async function availablePort() {
  const server = createServer();
  server.unref();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("could not allocate a test port");
  }
  const port = address.port;
  await new Promise((resolveClose) => server.close(resolveClose));
  return port;
}

async function waitFor(url, child, label) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null)
      throw new Error(`${label} exited before becoming ready`);
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(500) });
      if (response.ok) return;
    } catch {
      // The bounded retry loop handles ordinary startup races.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  throw new Error(`${label} did not become ready`);
}

async function stop(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    once(child, "exit"),
    new Promise((resolveDelay) => setTimeout(resolveDelay, 3_000)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

const temporaryRoot = await mkdtemp(join(tmpdir(), "agentbox-e2e-"));
const pairCanary = `PAIR-${randomBytes(18).toString("base64url").toUpperCase()}`;
let runError;

try {
  const [apiPort, webPort] = await Promise.all([
    availablePort(),
    availablePort(),
  ]);
  const apiOrigin = `http://127.0.0.1:${apiPort}`;
  const webOrigin = `http://127.0.0.1:${webPort}`;
  const testEnvironment = {
    ...process.env,
    // Vite preserves the browser Origin while its proxy may present either
    // loopback Host. Both are isolated, randomly allocated test origins.
    AGENTBOX_ALLOWED_ORIGINS: JSON.stringify([webOrigin, apiOrigin]),
    AGENTBOX_BIND_HOST: "127.0.0.1",
    AGENTBOX_BIND_PORT: String(apiPort),
    AGENTBOX_DATABASE_URL: `sqlite+pysqlite:///${join(temporaryRoot, "agentbox.db")}`,
    AGENTBOX_DATA_DIR: temporaryRoot,
    AGENTBOX_E2E_API_URL: apiOrigin,
    AGENTBOX_E2E_PASSWORD: `e2e-${randomBytes(24).toString("base64url")}`,
    AGENTBOX_E2E_PAIR_CODE: pairCanary,
    AGENTBOX_E2E_USERNAME: "e2e-maintainer",
    AGENTBOX_ENV: "test",
    AGENTBOX_PROJECT_ROOT: join(temporaryRoot, "projects"),
    AGENTBOX_SECRET_KEY: randomBytes(48).toString("base64url"),
    PLAYWRIGHT_BASE_URL: webOrigin,
    ...(authTiming
      ? {
          AGENTBOX_E2E_AUTH_TIMING: "1",
          AGENTBOX_E2E_TIMING_RESULTS: join(temporaryRoot, "auth-timing.jsonl"),
        }
      : {}),
  };

  await run(pythonCommand, ["-m", "alembic", "upgrade", "head"], {
    env: testEnvironment,
  });
  await run("pnpm", ["--filter", "@agentbox/web", "build"], {
    env: testEnvironment,
  });

  const api = start(
    pythonCommand,
    [
      "-m",
      "uvicorn",
      authTiming ? "e2e_auth_timing_app:app" : "e2e_app:app",
      "--app-dir",
      "tests",
      "--host",
      "127.0.0.1",
      "--port",
      String(apiPort),
      "--no-access-log",
    ],
    testEnvironment,
    authTiming,
  );
  await waitFor(`${apiOrigin}/readyz`, api, "API");

  const web = start(
    "pnpm",
    [
      "--filter",
      "@agentbox/web",
      "exec",
      "vite",
      "preview",
      "--host",
      "127.0.0.1",
      "--port",
      String(webPort),
      "--strictPort",
    ],
    testEnvironment,
  );
  await waitFor(webOrigin, web, "Web preview");

  await run(
    "pnpm",
    [
      "--filter", "@agentbox/web", "exec", "playwright", "test",
      ...(authTiming ? ["--config", "diagnostics/playwright.config.ts"] : []),
    ],
    {
      env: testEnvironment,
    },
  );
  if (authTiming) {
    const results = (
      await readFile(testEnvironment.AGENTBOX_E2E_TIMING_RESULTS, "utf8")
    ).trim().split("\n").map((line) => JSON.parse(line));
    if (results.length !== 4 || results.some((result) => result.passed !== 1)) {
      throw new Error("auth timing diagnostic failed; see numeric sample results");
    }
  }
} catch (error) {
  runError = error;
} finally {
  await Promise.all(children.map((child) => stop(child)));
  let canaryError;
  try {
    await assertCanaryAbsent(temporaryRoot, pairCanary);
    await assertCanaryAbsent(
      join(repositoryRoot, "apps", "web", "test-results"),
      pairCanary,
    );
    await assertCanaryAbsent(
      join(repositoryRoot, "apps", "web", "playwright-report"),
      pairCanary,
    );
    if (
      (await capture("git", ["diff", "--no-ext-diff"])).includes(
        Buffer.from(pairCanary),
      )
    ) {
      throw new Error("Pair Code canary persisted in the Git diff");
    }
  } catch (error) {
    canaryError = error;
  }
  await rm(temporaryRoot, { force: true, recursive: true });
  if (canaryError) {
    await Promise.all([
      rm(join(repositoryRoot, "apps", "web", "test-results"), {
        force: true,
        recursive: true,
      }),
      rm(join(repositoryRoot, "apps", "web", "playwright-report"), {
        force: true,
        recursive: true,
      }),
    ]);
    throw canaryError;
  }
}

if (runError) throw runError;
