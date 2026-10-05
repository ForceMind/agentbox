import { expect, test } from '@playwright/test'
import { A3NativeCounters, a3FixtureStatusNumbers } from './a3NativeCounters'

function control(prefix: string, length: number) {
  const raw = Buffer.alloc(length)
  raw.write(prefix, 0, 'ascii')
  raw[4] = 1
  return raw
}

test('fixed counters classify controls without retaining opaque content', () => {
  const counts = new A3NativeCounters()
  for (const event of [
    'sockets_created',
    'sockets_opened',
    'sockets_closed',
    'socket_errors',
  ] as const)
    counts.event(event)
  counts.frame('received', control('A3RD', 5))
  counts.frame('received', control('A3CR', 25))
  counts.frame('sent', control('A3CQ', 25))
  counts.frame('sent', control('A3CA', 41))
  counts.frame('sent', 'private-context-nonce-selector-key-canary')
  counts.frame('received', Buffer.from('private-patch-canary'))
  expect(Object.values(counts.snapshot())).toEqual(Array(10).fill(1))
  expect(JSON.stringify(counts.snapshot())).not.toContain('canary')
})

test('wrong direction length version and text are only opaque counts', () => {
  const counts = new A3NativeCounters()
  counts.frame('sent', control('A3RD', 5))
  counts.frame('received', control('A3CQ', 25))
  counts.frame('received', control('A3CR', 26))
  const wrongVersion = control('A3RD', 5)
  wrongVersion[4] = 2
  counts.frame('received', wrongVersion)
  counts.frame('received', 'A3RD\x01')
  expect(counts.snapshot().opaque_sent).toBe(1)
  expect(counts.snapshot().opaque_received).toBe(4)
  expect(counts.snapshot().ready_received).toBe(0)
  expect(counts.snapshot().current_received).toBe(0)
})

test('counts saturate and returned snapshots cannot mutate live counters', () => {
  const counts = new A3NativeCounters()
  for (let i = 0; i < 65_540; i++) counts.event('socket_errors')
  const before = counts.snapshot()
  counts.event('sockets_closed')
  expect(before.socket_errors).toBe(65_535)
  expect(before.sockets_closed).toBe(0)
  expect(counts.snapshot().sockets_closed).toBe(1)
  expect(Object.isFrozen(before)).toBe(true)
})

test('fixture diagnostics publish only bounded numeric allowlist', () => {
  const result = a3FixtureStatusNumbers({
    diff_count: 2,
    held: true,
    active: 1,
    burned_nonces: 1,
    connections: 2,
    secret: 'private-key-canary',
    patch: 'private-patch-canary',
    error: 'private-error-canary',
  })
  expect(result).toEqual({
    diff_count: 2,
    held: 1,
    active: 1,
    burned_nonces: 1,
    connections: 2,
  })
  expect(JSON.stringify(result)).not.toContain('canary')
  expect(
    a3FixtureStatusNumbers({
      diff_count: 'secret',
      held: 'secret',
      active: -5,
      burned_nonces: Infinity,
      connections: 2.5,
    }),
  ).toEqual({
    diff_count: -1,
    held: -1,
    active: -1,
    burned_nonces: -1,
    connections: -1,
  })
})
