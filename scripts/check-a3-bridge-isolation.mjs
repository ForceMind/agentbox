// Exercise the actual Playwright fixture bridge without launching a browser.
// A poisoned outer app environment must never override the child's isolated DB.
import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const ts = createRequire(join(root, 'apps/web/package.json'))('typescript')
const temporary = await mkdtemp(join(tmpdir(), 'a3-bridge-isolation-'))
const environment = { ...process.env }
let fixture
try {
  let source = await readFile(join(root, 'apps/web/e2e/a3FixtureBridge.ts'), 'utf8')
  // Keep the actual source module's dirname when transpiling to a temporary file.
  // This does not change the executed bridge body or replace its spawn/transport.
  source = source.replace('import.meta.dirname', JSON.stringify(join(root, 'apps/web/e2e')))
  const output = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } })
  const module = join(temporary, 'bridge.mjs')
  await writeFile(module, output.outputText)
  Object.assign(process.env, {
    AGENTBOX_ENV: 'production',
    AGENTBOX_DATABASE_URL: 'invalid-external-e2e-database',
    AGENTBOX_DATA_DIR: join(temporary, 'not-the-fixture-data'),
    AGENTBOX_PROJECT_ROOT: join(temporary, 'not-the-fixture-projects'),
    AGENTBOX_ALLOWED_ORIGINS: '["https://external-e2e.invalid"]',
    AGENTBOX_SECRET_KEY: 'synthetic-external-e2e-key-never-lent-to-child',
  })
  const { installA3Fixture } = await import(pathToFileURL(module).href)
  let exposed
  fixture = await installA3Fixture({ exposeFunction: async (name, callback) => {
    assert.equal(name, '__a3FixtureCall')
    exposed = callback
  } })
  assert.equal(typeof exposed, 'function')
  assert.equal((await exposed('status')).observations, 0)
  const trust = await exposed('trust')
  const metadata = await exposed('metadata')
  assert.equal(metadata.data.total_count, 5)
  const bootstrap = await exposed('bootstrap')
  assert.equal(bootstrap.schema_version, 'a3-staged-observation/v1')
  assert.deepEqual(bootstrap.binding, trust.binding)
  assert.equal((await exposed('status')).diff_count, 0)
  assert.equal(process.env.AGENTBOX_ENV, 'production')
  await fixture.close()
  fixture = undefined
  process.env.AGENTBOX_A3_PYTHON = join(temporary, 'missing-fixture-python')
  await assert.rejects(installA3Fixture({ exposeFunction: async () => {
    assert.fail('startup failure must not expose a bridge')
  } }), /A3 fixture bridge closed/)
  console.log('A3 actual Node bridge isolates outer app environment: PASS; no browser launched')
} finally {
  await fixture?.close()
  for (const key of Object.keys(process.env)) if (!(key in environment)) delete process.env[key]
  Object.assign(process.env, environment)
  await rm(temporary, { recursive: true, force: true })
}
