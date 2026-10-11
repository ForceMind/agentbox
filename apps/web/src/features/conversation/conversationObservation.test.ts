import { describe, expect, it } from 'vitest'
import vectors from '../../../../../tests/fixtures/kebui_observation/v1.json'
import {
  acceptConversationEvent,
  acceptConversationSnapshot,
  beginConversationRead,
  createConversationObservationState,
  interruptConversationObservation,
  parseConversationObservation,
  parseConversationScope,
} from './conversationObservation'

const view = 'a'.repeat(32)
const otherView = 'b'.repeat(32)
const base = vectors.base
const observation = (revision = '1', status = 'running') => ({
  ...structuredClone(base),
  revision,
  status,
})
function fresh(revision = '1', status = 'running') {
  const initial = createConversationObservationState(base.scope, view)
  return acceptConversationSnapshot(
    beginConversationRead(initial, '1'),
    view,
    '1',
    observation(revision, status),
  )
}

describe('isolated conversation metadata profile', () => {
  for (const vector of vectors.valid) {
    it(`accepts shared ${vector.name}`, () => {
      expect(parseConversationObservation(vector.value)).toEqual(vector.value)
    })
  }
  for (const vector of vectors.invalid_mutations) {
    it(`rejects shared ${vector.name}`, () => {
      const value = structuredClone(base) as unknown as Record<string, unknown>
      const target =
        vector.path.length === 2
          ? (value.scope as Record<string, unknown>)
          : value
      const key = vector.path.at(-1)!
      if (vector.op === 'delete') delete target[key]
      else target[key] = 'value' in vector ? vector.value : undefined
      expect(() => parseConversationObservation(value)).toThrow(
        'Invalid conversation observation',
      )
    })
  }
  it.each([null, [], true, 1, 'metadata', undefined])(
    'rejects a nonobject envelope %s',
    (value) => {
      expect(() => parseConversationObservation(value)).toThrow()
    },
  )
  it('copies and freezes all retained objects', () => {
    const input = observation()
    const parsed = parseConversationObservation(input)
    input.status = 'failed'
    input.scope.auth_epoch = '99'
    expect(parsed.status).toBe('running')
    expect(parsed.scope.auth_epoch).toBe('2')
    expect(Object.isFrozen(parsed)).toBe(true)
    expect(Object.isFrozen(parsed.scope)).toBe(true)
    const state = createConversationObservationState(base.scope, view)
    expect(Object.isFrozen(state)).toBe(true)
  })
  it('rejects nonplain objects, accessors, symbols and nonenumerable extra keys', () => {
    const inherited = Object.create(base)
    const getter = { ...base }
    Object.defineProperty(getter, 'status', {
      get: () => {
        throw new Error('getter must not run')
      },
    })
    const symbol = { ...base, [Symbol('body')]: 'hidden' }
    const hidden = { ...base }
    Object.defineProperty(hidden, 'body', { value: 'hidden' })
    for (const value of [inherited, getter, symbol, hidden])
      expect(() => parseConversationObservation(value)).toThrow(
        'Invalid conversation observation',
      )
  })
  it('rejects hidden required scope fields rather than dropping them while copying', () => {
    const scope = { ...base.scope }
    Object.defineProperty(scope, 'project_id', { enumerable: false })
    expect(() => parseConversationScope(scope)).toThrow(
      'Invalid conversation observation',
    )
  })
  it('rejects uppercase hexadecimal commitments', () => {
    for (const key of ['owner_scope', 'binding_digest'])
      expect(() =>
        parseConversationScope({ ...base.scope, [key]: 'A'.repeat(64) }),
      ).toThrow()
  })
  it('accepts a decoded null-prototype object without retaining its prototype', () => {
    const value = Object.assign(Object.create(null), base)
    expect(parseConversationObservation(value)).toEqual(base)
  })
})

describe('read-only observation projection', () => {
  it('requires an explicit initial snapshot and returns no action authority', () => {
    const state = createConversationObservationState(base.scope, view)
    expect(state.freshness).toBe('unobserved')
    expect(acceptConversationEvent(state, view, observation())).toBe(state)
    expect(Object.keys(state).sort()).toEqual(
      [
        'viewId',
        'scope',
        'observation',
        'freshness',
        'readFloor',
        'revisionFloor',
        'pendingRead',
      ].sort(),
    )
  })
  it.each(['', 'A'.repeat(32), 'a'.repeat(31), view + '\n', 1, null])(
    'rejects invalid view incarnation %s',
    (value) => {
      expect(() =>
        createConversationObservationState(base.scope, value),
      ).toThrow()
    },
  )
  it('ignores old view and superseded read attempts, including a reopened scope', () => {
    const state = beginConversationRead(
      beginConversationRead(
        createConversationObservationState(base.scope, view),
        '1',
      ),
      '2',
    )
    expect(acceptConversationSnapshot(state, view, '1', observation())).toBe(
      state,
    )
    expect(
      acceptConversationSnapshot(state, otherView, '2', observation()),
    ).toBe(state)
    const reopened = beginConversationRead(
      createConversationObservationState(base.scope, otherView),
      '1',
    )
    expect(acceptConversationSnapshot(reopened, view, '1', observation())).toBe(
      reopened,
    )
    expect(
      acceptConversationSnapshot(state, view, '2', observation()).freshness,
    ).toBe('fresh')
  })
  it('checks every scope field for snapshots and events', () => {
    const state = fresh()
    const reading = beginConversationRead(state, '2')
    for (const key of Object.keys(base.scope) as (keyof typeof base.scope)[]) {
      const value = observation('2')
      if (key === 'agent_type') value.scope[key] = 'claude'
      else if (key === 'execution_kind') {
        value.scope[key] = 'waw'
        expect(() => parseConversationScope(value.scope)).toThrow()
        continue
      } else if (key === 'owner_scope' || key === 'binding_digest')
        value.scope[key] = 'f'.repeat(64)
      else if (
        ['project_id', 'host_id', 'conversation_id', 'turn_id'].includes(key)
      )
        value.scope[key] = value.scope[key].slice(0, 4) + 'f'.repeat(32)
      else value.scope[key] = '99'
      expect(acceptConversationEvent(state, view, value)).toBe(state)
      expect(acceptConversationSnapshot(reading, view, '2', value)).toBe(
        reading,
      )
    }
  })
  it('treats identical duplicates and stale observations as no-ops', () => {
    const state = fresh('2')
    expect(acceptConversationEvent(state, view, observation('2'))).toBe(state)
    expect(
      acceptConversationEvent(state, view, observation('1', 'failed')),
    ).toBe(state)
    const reading = beginConversationRead(state, '2')
    expect(
      acceptConversationSnapshot(reading, view, '2', observation('1')),
    ).toBe(reading)
  })
  it('fences gaps until an explicit matching read snapshot', () => {
    const state = fresh()
    const gap = acceptConversationEvent(
      state,
      view,
      observation('3', 'completed'),
    )
    expect(gap.freshness).toBe('incomplete')
    expect(gap.observation?.revision).toBe('1')
    expect(acceptConversationEvent(gap, view, observation('2'))).toBe(gap)
    expect(acceptConversationSnapshot(gap, view, '1', observation('3'))).toBe(
      gap,
    )
    const result = acceptConversationSnapshot(
      beginConversationRead(gap, '2'),
      view,
      '2',
      observation('3', 'completed'),
    )
    expect(result.freshness).toBe('fresh')
    expect(result.observation?.status).toBe('completed')
  })
  it('does not clear a known gap with a lower-revision read snapshot', () => {
    const gap = acceptConversationEvent(
      fresh(),
      view,
      observation('3', 'completed'),
    )
    const reading = beginConversationRead(gap, '2')
    expect(
      acceptConversationSnapshot(reading, view, '2', observation('1')),
    ).toBe(reading)
    expect(
      acceptConversationSnapshot(reading, view, '2', observation('2')),
    ).toBe(reading)
    const hidden = interruptConversationObservation(reading)
    const returned = beginConversationRead(hidden, '3')
    expect(
      acceptConversationSnapshot(returned, view, '3', observation('2')),
    ).toBe(returned)
    const recovered = acceptConversationSnapshot(
      returned,
      view,
      '3',
      observation('3', 'completed'),
    )
    expect(recovered.freshness).toBe('fresh')
    expect(recovered.observation?.revision).toBe('3')
  })
  it('makes same-revision conflicts sticky across reads and interruption', () => {
    const conflict = acceptConversationEvent(
      fresh(),
      view,
      observation('1', 'failed'),
    )
    expect(conflict.freshness).toBe('conflict')
    expect(beginConversationRead(conflict, '2')).toBe(conflict)
    expect(interruptConversationObservation(conflict)).toBe(conflict)
    expect(
      acceptConversationSnapshot(conflict, view, '1', observation('2')),
    ).toBe(conflict)
  })
  it.each(['completed', 'failed', 'canceled'])(
    'never revives terminal %s',
    (status) => {
      const state = fresh('3', status)
      expect(
        acceptConversationEvent(state, view, observation('4')).freshness,
      ).toBe('conflict')
      const reading = beginConversationRead(state, '2')
      expect(
        acceptConversationSnapshot(reading, view, '2', observation('4'))
          .freshness,
      ).toBe('conflict')
      expect(
        acceptConversationEvent(state, view, observation('4', status))
          .observation?.status,
      ).toBe(status)
    },
  )
  it('invalidates pending reads on interruption and preserves the attempt floor', () => {
    const reading = beginConversationRead(fresh(), '2')
    const hidden = interruptConversationObservation(reading)
    expect(hidden.freshness).toBe('stale')
    expect(hidden.pendingRead).toBeNull()
    expect(beginConversationRead(hidden, '2')).toBe(hidden)
    expect(
      acceptConversationSnapshot(hidden, view, '2', observation('2')),
    ).toBe(hidden)
    expect(acceptConversationEvent(hidden, view, observation('2'))).toBe(hidden)
    const read = beginConversationRead(hidden, '3')
    expect(
      acceptConversationSnapshot(read, view, '3', observation('2')).freshness,
    ).toBe('fresh')
  })
  it.each(['0', '01', '1\n', '18446744073709551616', 1, true, null])(
    'rejects malformed read attempt %s',
    (value) => {
      expect(() => beginConversationRead(fresh(), value)).toThrow()
    },
  )
  it('supports uint64 ceiling without wrapping', () => {
    const state = fresh('18446744073709551615')
    expect(
      acceptConversationEvent(state, view, observation('18446744073709551615')),
    ).toBe(state)
    const reading = beginConversationRead(state, '18446744073709551615')
    expect(beginConversationRead(reading, '18446744073709551615')).toBe(reading)
  })
  it('does not retain caller mutations or arbitrary content', () => {
    const value = observation('2')
    const result = acceptConversationEvent(fresh(), view, value)
    value.scope.auth_epoch = '99'
    value.status = 'failed'
    expect(result.observation?.status).toBe('running')
    expect(result.scope.auth_epoch).toBe('2')
    expect(() =>
      acceptConversationEvent(result, view, {
        ...observation('3'),
        body: 'untrusted',
      }),
    ).toThrow()
    expect(result.observation?.revision).toBe('2')
  })
})
