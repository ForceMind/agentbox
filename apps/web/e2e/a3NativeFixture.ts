/** Separate-process CI fixture. Never imported by App or any production bundle. */
import { spawn, execFileSync } from 'node:child_process'
import { once } from 'node:events'
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from 'node:fs/promises'
import { request as httpRequest } from 'node:http'
import { createServer } from 'node:https'
import { connect, createServer as createTcpServer } from 'node:net'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { chromium, type BrowserContext, type TestInfo } from '@playwright/test'

import { preserveFixtureFailure, runFixtureCleanup } from './a3FixtureCleanup'

const root = resolve(import.meta.dirname, '../../..')
const bootstrapPath = '/.well-known/agentbox/a3-bootstrap.v1.json'
const build = 'd'.repeat(64)
const pin = '8f40c5adb68f25624ae5b214ea767a6ec94d829d3d7b5e1ad1ba6f3e2138285f'
export type StaticMode =
  | 'normal'
  | 'missing-markers'
  | 'missing'
  | 'malformed'
  | 'oversize'
  | 'redirect'
  | 'changed'
  | 'mismatch'
  | 'wrong-origin'
  | 'expired'

type Started = {
  api_origin: string
  certificate: string
  tls_key: string
  proof: Record<string, unknown>
}
type Reply = {
  id: number
  ok: boolean
  code?: string
  stage?: string
  role?: string
  phase?: string
  child_code?: string
  primary_code?: string
  cleanup_failed?: boolean
  result: unknown
}

export async function startA3NativeFixture(testInfo: TestInfo) {
  const temporary = await mkdtemp(join(tmpdir(), 'a3n-'))
  // Numeric API/Runtime UIDs need traversal, never directory write access.
  await chmod(temporary, 0o755)
  const staticRoot = join(temporary, 'static')
  await mkdir(staticRoot)
  const originalIndex = await readFile(
    join(root, 'apps/web/dist/index.html'),
    'utf8',
  )
  const index = originalIndex.replace(
    '</head>',
    `<meta name="agentbox-a3-trust-profile" content="a3-https-web-v1"><meta name="agentbox-a3-build-identity" content="${build}"></head>`,
  )
  await writeFile(join(staticRoot, 'index.html'), index, { mode: 0o444 })
  await chmod(staticRoot, 0o555)
  const assets = new Map<string, Buffer>()
  async function loadAssets(directory: string, prefix = '') {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      const key = `${prefix}/${entry.name}`
      if (entry.isDirectory()) await loadAssets(path, key)
      else assets.set(key, await readFile(path))
    }
  }
  await loadAssets(join(root, 'apps/web/dist'))
  const portOwner = createTcpServer()
  portOwner.listen(0, '127.0.0.1')
  await once(portOwner, 'listening')
  const address = portOwner.address()
  if (!address || typeof address === 'string')
    throw new Error('fixture port unavailable')
  const port = address.port
  await new Promise<void>((resolveClose) =>
    portOwner.close(() => resolveClose()),
  )
  const origin = `https://127.0.0.1:${port}`
  const isolated =
    Boolean(process.env.CI) || process.env.AGENTBOX_A3_NATIVE_ISOLATION === '1'
  const python =
    process.env.AGENTBOX_A3_PYTHON ??
    execFileSync('which', ['python'], { encoding: 'utf8' }).trim()
  const executable = isolated ? 'sudo' : python
  const arguments_ = isolated
    ? [
        '-n',
        'env',
        `PATH=${process.env.PATH ?? ''}`,
        `PYTHONPATH=${process.env.PYTHONPATH ?? ''}`,
        python,
        'tests/interop/a3_native_peer.py',
      ]
    : ['tests/interop/a3_native_peer.py']
  const child = spawn(executable, arguments_, {
    cwd: root,
    env: process.env,
    stdio: ['pipe', 'pipe', 'ignore'],
  })
  const pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (error: Error) => void }
  >()
  let next = 0
  let buffered = ''
  let exited = false
  let controlClosed = false
  const rejectAll = () => {
    controlClosed = true
    for (const item of Array.from(pending.values()))
      item.reject(new Error('native fixture exited'))
    pending.clear()
  }
  child.on('error', rejectAll)
  child.on('exit', () => {
    exited = true
  })
  // Drain stdout before rejecting pending controls: the final cleanup ACK may
  // already be in the pipe when the process exit notification arrives.
  child.on('close', rejectAll)
  child.stdin.on('error', rejectAll)
  child.stdout.on('data', (chunk: Buffer) => {
    buffered += chunk.toString('utf8')
    if (buffered.length > 65536) {
      child.kill()
      rejectAll()
      return
    }
    let newline: number
    while ((newline = buffered.indexOf('\n')) >= 0) {
      const line = buffered.slice(0, newline)
      buffered = buffered.slice(newline + 1)
      try {
        const reply = JSON.parse(line) as Reply
        const item = pending.get(reply.id)
        if (!item) throw new Error('unknown fixture response')
        pending.delete(reply.id)
        if (reply.ok) item.resolve(reply.result)
        else
          item.reject(
            new Error(
              `native fixture ${[reply.stage, reply.role, reply.phase, reply.child_code, reply.primary_code, reply.code, reply.cleanup_failed ? 'cleanup-failed' : undefined].filter(Boolean).join(':') || 'failed'}`,
            ),
          )
      } catch {
        child.kill()
        rejectAll()
      }
    }
  })
  const call = (op: string, payload: Record<string, unknown> = {}) => {
    if (controlClosed || exited || pending.size >= 4)
      return Promise.reject(new Error('native fixture unavailable'))
    const id = ++next
    return new Promise<unknown>((resolveCall, rejectCall) => {
      const timer = setTimeout(() => {
        pending.delete(id)
        rejectCall(new Error('native fixture control timed out'))
      }, 15000)
      pending.set(id, {
        resolve(value) {
          clearTimeout(timer)
          resolveCall(value)
        },
        reject(error) {
          clearTimeout(timer)
          rejectCall(error)
        },
      })
      child.stdin.write(JSON.stringify({ id, op, ...payload }) + '\n')
    })
  }
  let context: BrowserContext | undefined
  let server: ReturnType<typeof createServer> | undefined
  const sockets = new Set<import('node:stream').Duplex>()
  let closing: Promise<void> | undefined
  const close = () => {
    if (closing) return closing
    let supervisorClean = false
    closing = runFixtureCleanup([
      async () => {
        await context?.close()
      },
      async () => {
        for (const socket of Array.from(sockets)) socket.destroy()
        if (server)
          await new Promise<void>((resolveClose) =>
            server!.close(() => resolveClose()),
          )
      },
      async () => {
        const result = (await call('close')) as { cleaned?: boolean }
        if (result.cleaned !== true)
          throw new Error('supervisor cleanup was not confirmed')
        supervisorClean = true
      },
      async () => {
        child.stdin.end()
        if (!exited)
          await Promise.race([
            once(child, 'exit'),
            new Promise<void>((done) => setTimeout(done, 3000)),
          ])
        if (!exited) {
          child.kill()
          throw new Error(
            'native fixture supervisor did not exit after cleanup',
          )
        }
      },
      async () => {
        // The privileged owner removed its fixed processes subtree already.
        // Do not attempt unprivileged recursive cleanup after an unconfirmed ACK.
        if (supervisorClean)
          await rm(temporary, { recursive: true, force: true })
      },
    ])
    return closing
  }
  return preserveFixtureFailure(async () => {
    const started = (await call('start', {
      root: temporary,
      static_root: staticRoot,
      origin,
      isolated,
    })) as Started
    let mode: StaticMode = 'normal'
    const counts = { bootstrap: 0, observations: 0, websockets: 0 }
    const now = Date.now()
    const document = {
      schema_version: 'agentbox-a3-https-bootstrap.v1',
      trust_profile: 'a3-https-web-v1',
      purpose: 'agentbox-a3-content/crypto/v2',
      repository: 'ForceMind/agentbox',
      origin,
      runtime_host_installation_id: `wri_${'c'.repeat(32)}`,
      runtime_host_installation_revision: '1',
      runtime_attestation_x25519_public_key: pin,
      host_manifest_digest: 'a'.repeat(64),
      build_identity: build,
      version: '0.3.0',
      valid_from: new Date(now - 60_000).toISOString().replace('.000Z', 'Z'),
      valid_until: new Date(now + 3_600_000)
        .toISOString()
        .replace('.000Z', 'Z'),
    }
    // Exact UTC seconds, canonical sorted ASCII JSON plus one newline.
    document.valid_from = new Date(Math.floor((now - 60_000) / 1000) * 1000)
      .toISOString()
      .replace('.000Z', 'Z')
    document.valid_until = new Date(Math.floor((now + 3_600_000) / 1000) * 1000)
      .toISOString()
      .replace('.000Z', 'Z')
    const bootstrap = () => {
      const value = { ...document }
      if (mode === 'changed' || (mode === 'mismatch' && counts.bootstrap > 1))
        value.version = '0.3.1'
      if (mode === 'wrong-origin') value.origin = 'https://wrong.invalid'
      if (mode === 'expired') value.valid_until = value.valid_from
      return (
        JSON.stringify(
          Object.fromEntries(
            Object.entries(value).sort(([a], [b]) =>
              a < b ? -1 : a > b ? 1 : 0,
            ),
          ),
        ) + '\n'
      )
    }
    server = createServer(
      { cert: started.certificate, key: started.tls_key },
      (request, response) => {
        const path = new URL(request.url ?? '/', origin).pathname
        if (
          path.startsWith('/api/') ||
          path === '/readyz' ||
          path === '/healthz'
        ) {
          if (path.endsWith('/git/staged-observation')) counts.observations++
          const upstream = httpRequest(
            `${started.api_origin}${request.url}`,
            {
              method: request.method,
              headers: { ...request.headers, 'x-forwarded-proto': 'https' },
            },
            (reply) => {
              response.writeHead(reply.statusCode ?? 502, reply.headers)
              reply.pipe(response)
            },
          )
          upstream.on('error', () => {
            response.writeHead(502)
            response.end()
          })
          request.pipe(upstream)
          return
        }
        response.setHeader('Cache-Control', 'no-store')
        if (path === bootstrapPath) {
          counts.bootstrap++
          if (mode === 'missing') {
            response.writeHead(404)
            response.end()
            return
          }
          if (mode === 'redirect') {
            response.writeHead(302, { Location: '/redirected-bootstrap' })
            response.end()
            return
          }
          response.setHeader('Content-Type', 'application/json')
          response.end(
            mode === 'malformed'
              ? '{"invalid":true}\n'
              : mode === 'oversize'
                ? 'x'.repeat(8193)
                : bootstrap(),
          )
          return
        }
        const asset = assets.get(path)
        if (asset && path !== '/index.html') {
          response.setHeader(
            'Content-Type',
            path.endsWith('.js')
              ? 'text/javascript'
              : path.endsWith('.css')
                ? 'text/css'
                : 'application/octet-stream',
          )
          response.end(asset)
          return
        }
        response.setHeader('Content-Type', 'text/html; charset=utf-8')
        response.end(mode === 'missing-markers' ? originalIndex : index)
      },
    )
    server.on('connection', (socket) => {
      sockets.add(socket)
      socket.on('close', () => sockets.delete(socket))
    })
    server.on('upgrade', (request, downstream, head) => {
      counts.websockets++
      const target = new URL(started.api_origin)
      const upstream = connect(Number(target.port), target.hostname)
      sockets.add(upstream)
      upstream.on('close', () => sockets.delete(upstream))
      upstream.on('error', () => downstream.destroy())
      downstream.on('error', () => upstream.destroy())
      downstream.on('close', () => upstream.destroy())
      upstream.once('connect', () => {
        const headers = Object.entries({
          ...request.headers,
          'x-forwarded-proto': 'https',
        }).flatMap(([name, value]) =>
          Array.isArray(value)
            ? value.map((item) => `${name}: ${item}`)
            : [`${name}: ${value}`],
        )
        upstream.write(
          `GET ${request.url} HTTP/1.1\r\n${headers.join('\r\n')}\r\n\r\n`,
        )
        if (head.length) upstream.write(head)
        downstream.pipe(upstream).pipe(downstream)
      })
    })
    server.listen(port, '127.0.0.1')
    await once(server, 'listening')
    // Synthetic TLS only. Chromium's documented NSS exact-leaf trust is scoped
    // to this disposable HOME, with no TLS-warning bypass or real-user store.
    // https://chromium.googlesource.com/chromium/src.git/+/master/docs/linux/cert_management.md
    const home = join(temporary, 'browser-home')
    const nss = join(home, '.pki/nssdb')
    const certificate = join(temporary, 'fixture-leaf.pem')
    await mkdir(nss, { recursive: true })
    await writeFile(certificate, started.certificate)
    execFileSync('certutil', ['-N', '-d', `sql:${nss}`, '--empty-password'])
    execFileSync('certutil', [
      '-A',
      '-d',
      `sql:${nss}`,
      '-n',
      'a3-ci-exact-leaf',
      '-t',
      'P,,',
      '-i',
      certificate,
    ])
    context = await chromium.launchPersistentContext(
      join(temporary, 'chromium-profile'),
      {
        viewport: testInfo.project.use.viewport,
        isMobile: testInfo.project.use.isMobile,
        hasTouch: testInfo.project.use.hasTouch,
        deviceScaleFactor: testInfo.project.use.deviceScaleFactor,
        userAgent: testInfo.project.use.userAgent,
        locale: 'zh-CN',
        env: {
          ...process.env,
          HOME: home,
          XDG_DATA_HOME: join(home, '.local/share'),
        },
      },
    )
    const page = context.pages()[0] ?? (await context.newPage())
    return {
      page,
      context,
      origin,
      call,
      counts,
      proof: started.proof,
      close,
      setStaticMode(value: StaticMode) {
        mode = value
      },
    }
  }, close)
}
