import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const repositoryRoot = resolve(import.meta.dirname, "..");
const pythonBin = join(repositoryRoot, ".venv", "bin");
const children = [];

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

function start(command, args, env) {
  const child = spawn(command, args, {
    cwd: repositoryRoot,
    env,
    stdio: "inherit",
  });
  children.push(child);
  return child;
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
    AGENTBOX_E2E_USERNAME: "e2e-maintainer",
    AGENTBOX_ENV: "test",
    AGENTBOX_SECRET_KEY: randomBytes(48).toString("base64url"),
    PLAYWRIGHT_BASE_URL: webOrigin,
  };

  await run(join(pythonBin, "alembic"), ["upgrade", "head"], {
    env: testEnvironment,
  });
  await run("pnpm", ["--filter", "@agentbox/web", "build"], {
    env: testEnvironment,
  });

  const api = start(
    join(pythonBin, "uvicorn"),
    [
      "e2e_app:app",
      "--app-dir",
      "tests",
      "--host",
      "127.0.0.1",
      "--port",
      String(apiPort),
      "--no-access-log",
    ],
    testEnvironment,
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
    ["--filter", "@agentbox/web", "exec", "playwright", "test"],
    {
      env: testEnvironment,
    },
  );
} finally {
  await Promise.all(children.map((child) => stop(child)));
  await rm(temporaryRoot, { force: true, recursive: true });
}
