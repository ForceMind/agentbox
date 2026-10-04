/** Isolated Node↔Python software fixture. Never imported by the production app. */
import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
import type { Page } from '@playwright/test'

type Reply = {
  id?: number
  ready?: boolean
  ok?: boolean
  result?: unknown
  code?: string
}

export async function installA3Fixture(page: Page) {
  const root = resolve(import.meta.dirname, '../../..')
  const child = spawn(
    process.env.AGENTBOX_A3_PYTHON ?? 'python',
    ['tests/interop/a3_changes_peer.py'],
    { cwd: root, stdio: ['pipe', 'pipe', 'ignore'] },
  )
  let counter = 0
  let buffered = ''
  let closed = false
  const pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (error: Error) => void }
  >()
  let readyResolve!: () => void
  let readyReject!: (error: Error) => void
  const ready = new Promise<void>((resolveReady, rejectReady) => {
    readyResolve = resolveReady
    readyReject = rejectReady
  })
  const rejectAll = () => {
    closed = true
    const error = new Error('A3 fixture bridge closed')
    readyReject(error)
    for (const entry of Array.from(pending.values())) entry.reject(error)
    pending.clear()
  }
  child.once('error', rejectAll)
  child.once('exit', rejectAll)
  child.stdout.on('data', (chunk: Buffer) => {
    buffered += chunk.toString('utf8')
    if (Buffer.byteLength(buffered) > 2 * 1024 * 1024) {
      child.kill()
      rejectAll()
      return
    }
    let newline: number
    while ((newline = buffered.indexOf('\n')) >= 0) {
      const line = buffered.slice(0, newline)
      buffered = buffered.slice(newline + 1)
      try {
        const message = JSON.parse(line) as Reply
        if (message.ready === true) {
          readyResolve()
          continue
        }
        const entry = pending.get(message.id!)
        if (!entry) throw new Error('unknown response')
        pending.delete(message.id!)
        if (message.ok) entry.resolve(message.result)
        else entry.reject(new Error(message.code ?? 'PATCH_PROTOCOL_INVALID'))
      } catch {
        child.kill()
        rejectAll()
        return
      }
    }
  })
  const readyTimer = setTimeout(() => {
    child.kill()
    rejectAll()
  }, 10_000)
  try {
    await ready
  } finally {
    clearTimeout(readyTimer)
  }
  const call = (op: string, payload: Record<string, unknown> = {}) => {
    if (closed || pending.size >= 8)
      return Promise.reject(new Error('A3 fixture bridge unavailable'))
    const id = ++counter
    const wire = JSON.stringify({ id, op, payload }) + '\n'
    if (Buffer.byteLength(wire) > 50_176)
      return Promise.reject(new Error('A3 fixture request exceeded bound'))
    return new Promise<unknown>((resolveCall, rejectCall) => {
      const timer = setTimeout(() => {
        pending.delete(id)
        rejectCall(new Error('A3 fixture request expired'))
        child.kill()
      }, 35_000)
      pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer)
          resolveCall(value)
        },
        reject: (error) => {
          clearTimeout(timer)
          rejectCall(error)
        },
      })
      child.stdin.write(wire)
    })
  }
  await page.exposeFunction('__a3FixtureCall', call)
  const close = async () => {
    if (closed) return
    await call('release').catch(() => undefined)
    await call('close').catch(() => undefined)
    child.stdin.end()
    if (!closed) {
      await new Promise<void>((resolveExit) => {
        const timer = setTimeout(() => child.kill(), 2000)
        child.once('exit', () => {
          clearTimeout(timer)
          resolveExit()
        })
      })
    }
  }
  return { call, close }
}
