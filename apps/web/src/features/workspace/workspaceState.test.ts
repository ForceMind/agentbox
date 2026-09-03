import { describe, expect, it } from 'vitest'
import {
  initialWorkspaceState,
  isCanonicalUint64,
  workspaceReducer,
  type WorkspaceAction,
  type WorkspaceFence,
  type WorkspaceState,
} from './workspaceState'

const projectId = 'prj_' + '1'.repeat(32)
const workspaceId = 'aws_' + '2'.repeat(32)
const fence: WorkspaceFence = {
  projectId,
  workspaceId,
  agentType: 'claude',
  sessionId: 'ses_test',
  generation: '1',
  bindingRevision: '1',
  bindingDigest: 'a'.repeat(64),
  hostId: 'wri_' + '3'.repeat(32),
  hostRevision: '1',
  runtimeEpoch: '4',
  apiAuthorityEpoch: '20',
  sessionAuthEpoch: '1',
}
const attachment = { attachmentId: 'att_' + '4'.repeat(32), leaseNumber: '8' }
const event = { fence, attachment }
function accepted(): WorkspaceState {
  return workspaceReducer(
    workspaceReducer(initialWorkspaceState, {
      type: 'start_requested',
      projectId,
      attempt: '1',
    }),
    { type: 'start_accepted', projectId, workspaceId, attempt: '1', fence },
  )
}
function prepared(): WorkspaceState {
  return workspaceReducer(
    workspaceReducer(accepted(), {
      type: 'connecting',
      attempt: '2',
    }),
    { type: 'attachment_prepared', attempt: '2', event },
  )
}
function connected(): WorkspaceState {
  const state = workspaceReducer(prepared(), { type: 'admitted', event })
  expect(state.status).toBe('connected')
  return state
}
function stopped(): WorkspaceState {
  return workspaceReducer(
    workspaceReducer(connected(), {
      type: 'stop_requested',
      attempt: '3',
    }),
    { type: 'stopped', attempt: '3', fence },
  )
}

describe('Workspace recovery reducer', () => {
  it('requires an explicit connection request and exact admission after HTTP success', () => {
    const state = accepted()
    expect(state.status).toBe('connecting')
    expect(
      workspaceReducer(state, {
        type: 'attachment_prepared',
        attempt: '2',
        event,
      }),
    ).toBe(state)
    expect(workspaceReducer(state, { type: 'admitted', event })).toBe(state)
    expect(connected().status).toBe('connected')
  })

  it.each<unknown>([
    0,
    1,
    true,
    null,
    undefined,
    '',
    '00',
    '01',
    '-1',
    '1.0',
    '١',
    '1\n',
    '18446744073709551616',
    '9'.repeat(100_000),
  ])('rejects malformed uint64 %s', (value) => {
    expect(isCanonicalUint64(value)).toBe(false)
  })
  it('preserves full uint64 precision and separates the zero sentinel', () => {
    expect(isCanonicalUint64('0')).toBe(true)
    expect(isCanonicalUint64('0', true)).toBe(false)
    expect(isCanonicalUint64('18446744073709551615', true)).toBe(true)
  })

  it.each<[keyof WorkspaceFence, string]>([
    ['projectId', 'prj_' + '9'.repeat(32)],
    ['workspaceId', 'aws_' + '9'.repeat(32)],
    ['agentType', 'codex'],
    ['sessionId', 'ses_other'],
    ['generation', '2'],
    ['bindingRevision', '2'],
    ['bindingDigest', 'b'.repeat(64)],
    ['hostId', 'wri_' + '9'.repeat(32)],
    ['hostRevision', '2'],
    ['runtimeEpoch', '5'],
    ['apiAuthorityEpoch', '21'],
    ['sessionAuthEpoch', '2'],
  ])('rejects every stale async event with different %s', (key, value) => {
    const state = connected()
    const stale = { ...event, fence: { ...fence, [key]: value } }
    const actions: WorkspaceAction[] = [
      { type: 'admitted', event: stale },
      { type: 'detached', event: stale },
      { type: 'input_uncertain', event: stale },
      { type: 'gap', event: stale, fromCursor: '1', toCursor: '3' },
      { type: 'output_observed', event: stale, cursor: '2' },
      { type: 'error', event: stale, message: 'stale' },
      { type: 'exited', event: stale, message: 'stale' },
    ]
    for (const action of actions)
      expect(workspaceReducer(state, action)).toBe(state)
    const stopping = workspaceReducer(state, {
      type: 'stop_requested',
      attempt: '3',
    })
    expect(
      workspaceReducer(stopping, {
        type: 'stopped',
        attempt: '3',
        fence: stale.fence,
      }),
    ).toBe(stopping)
  })

  it.each<Partial<WorkspaceFence>>([
    { hostId: 'host-1' },
    { bindingDigest: 'x' },
    { sessionId: '' },
    { sessionId: 'x'.repeat(129) },
    { generation: '0' },
    { runtimeEpoch: '18446744073709551616' },
    { agentType: 'shell' as 'claude' },
    { bindingRevision: '01' },
  ])('rejects malformed metadata before binding a workspace: %j', (patch) => {
    const starting = workspaceReducer(initialWorkspaceState, {
      type: 'start_requested',
      projectId,
      attempt: '1',
    })
    expect(
      workspaceReducer(starting, {
        type: 'start_accepted',
        projectId,
        workspaceId,
        attempt: '1',
        fence: { ...fence, ...patch },
      }),
    ).toBe(starting)
  })

  it('fences late Start responses and inconsistent response identities', () => {
    const state = workspaceReducer(
      workspaceReducer(initialWorkspaceState, {
        type: 'start_requested',
        projectId,
        attempt: '1',
      }),
      { type: 'start_requested', projectId, attempt: '2' },
    )
    expect(
      workspaceReducer(state, {
        type: 'start_accepted',
        projectId,
        workspaceId,
        attempt: '1',
        fence,
      }),
    ).toBe(state)
    expect(
      workspaceReducer(state, {
        type: 'start_accepted',
        projectId,
        workspaceId: 'aws_' + '9'.repeat(32),
        attempt: '2',
        fence,
      }),
    ).toBe(state)
    expect(
      workspaceReducer(state, {
        type: 'start_accepted',
        projectId,
        workspaceId,
        attempt: '2',
        fence: { ...fence, agentType: 'codex' },
      }),
    ).toBe(state)
    expect(
      workspaceReducer(state, {
        type: 'request_failed',
        operation: 'start',
        attempt: '1',
        code: 'OLD',
        message: 'old',
      }),
    ).toBe(state)
  })

  it('correlates prepared callbacks and never reuses or replaces an active lease', () => {
    const state = workspaceReducer(connected(), {
      type: 'reconnect_requested',
      attempt: '3',
    })
    const nextEvent = {
      fence,
      attachment: { attachmentId: 'att_' + '5'.repeat(32), leaseNumber: '9' },
    }
    expect(
      workspaceReducer(state, {
        type: 'attachment_prepared',
        attempt: '2',
        event: nextEvent,
      }),
    ).toBe(state)
    expect(
      workspaceReducer(state, {
        type: 'attachment_prepared',
        attempt: '3',
        event,
      }),
    ).toBe(state)
    expect(
      workspaceReducer(state, {
        type: 'attachment_prepared',
        attempt: '3',
        event: {
          ...nextEvent,
          attachment: { ...nextEvent.attachment, leaseNumber: '8' },
        },
      }),
    ).toBe(state)
    const fresh = workspaceReducer(state, {
      type: 'attachment_prepared',
      attempt: '3',
      event: nextEvent,
    })
    expect(
      workspaceReducer(fresh, {
        type: 'attachment_prepared',
        attempt: '3',
        event,
      }),
    ).toBe(fresh)
    expect(workspaceReducer(fresh, { type: 'admitted', event })).toBe(fresh)
    expect(
      workspaceReducer(fresh, { type: 'admitted', event: nextEvent }).status,
    ).toBe('connected')
  })

  it('advances only explicit observed output and treats duplicate or older output as a no-op', () => {
    const state = connected()
    const output = workspaceReducer(state, {
      type: 'output_observed',
      event,
      cursor: '9',
    })
    expect(output.cursor).toBe('9')
    expect(output.status).toBe('connected')
    for (const cursor of [
      '0',
      '8',
      '9',
      '18446744073709551615',
      '18446744073709551616',
    ]) {
      expect(
        workspaceReducer(output, { type: 'output_observed', event, cursor }),
      ).toBe(output)
    }
    expect(workspaceReducer(output, { type: 'admitted', event })).toBe(output)
  })

  it('accepts only explicit same-stream half-open GAP and makes replay idempotent', () => {
    const output = workspaceReducer(connected(), {
      type: 'output_observed',
      event,
      cursor: '4',
    })
    const gap = { type: 'gap' as const, event, fromCursor: '5', toCursor: '9' }
    const state = workspaceReducer(output, gap)
    expect(state.status).toBe('gap')
    expect(state.cursor).toBe('8')
    expect(workspaceReducer(state, gap)).toBe(state)
    for (const [fromCursor, toCursor] of [
      ['0', '1'],
      ['6', '8'],
      ['9', '9'],
      ['9', '8'],
      ['10', '12'],
      ['9', '18446744073709551616'],
    ]) {
      expect(
        workspaceReducer(state, { type: 'gap', event, fromCursor, toCursor }),
      ).toBe(state)
    }
  })

  it('accepts random API epoch rotation even when its numeric value decreases', () => {
    const state = connected()
    const next = { ...fence, apiAuthorityEpoch: '3' }
    const restarted = workspaceReducer(state, {
      type: 'api_restarted',
      previous: fence,
      next,
    })
    expect(restarted.status).toBe('reconnecting')
    expect(restarted.workspaceFence?.runtimeEpoch).toBe('4')
    expect(restarted.attachmentFence).toBeNull()
    expect(
      workspaceReducer(restarted, {
        type: 'api_restarted',
        previous: fence,
        next,
      }),
    ).toBe(restarted)
    expect(workspaceReducer(restarted, { type: 'admitted', event })).toBe(
      restarted,
    )
  })

  it('keeps Runtime recovery mandatory across API rotation and requires a newer reconciled generation', () => {
    const next = { ...fence, runtimeEpoch: '5' }
    const state = workspaceReducer(connected(), {
      type: 'runtime_restarted',
      previous: fence,
      next,
    })
    expect(state.recoveryRequired).toBe(true)
    expect(state.status).toBe('unavailable')
    expect(state.cursor).toBeNull()
    for (const action of [
      { type: 'reconnect_requested', attempt: '3' },
      { type: 'start_requested', attempt: '3', projectId },
      {
        type: 'attachment_prepared',
        attempt: '2',
        event: { ...event, fence: next },
      },
      { type: 'admitted', event: { ...event, fence: next } },
      { type: 'recovery_reconciled', previous: next, next },
    ] as WorkspaceAction[])
      expect(workspaceReducer(state, action)).toBe(state)
    const apiNext = { ...next, apiAuthorityEpoch: '2' }
    const rotated = workspaceReducer(state, {
      type: 'api_restarted',
      previous: next,
      next: apiNext,
    })
    expect(rotated.recoveryRequired).toBe(true)
    expect(rotated.status).toBe('unavailable')
    const reconciled = workspaceReducer(rotated, {
      type: 'recovery_reconciled',
      previous: apiNext,
      next: { ...apiNext, generation: '2' },
    })
    expect(reconciled.recoveryRequired).toBe(false)
    expect(reconciled.status).toBe('detached')
  })

  it('rejects a late or decreasing Runtime epoch without losing the current attachment', () => {
    const state = connected()
    for (const runtimeEpoch of ['3', '4'])
      expect(
        workspaceReducer(state, {
          type: 'runtime_restarted',
          previous: fence,
          next: { ...fence, runtimeEpoch },
        }),
      ).toBe(state)
  })

  it('freezes a background page and never silently reconnects or replays input', () => {
    const state = workspaceReducer(connected(), {
      type: 'input_uncertain',
      event,
    })
    expect(state.status).toBe('input_uncertain')
    const hidden = workspaceReducer(state, {
      type: 'visibility_changed',
      visible: false,
    })
    expect(hidden.attachmentFence).toBeNull()
    expect(
      workspaceReducer(hidden, { type: 'visibility_changed', visible: true }),
    ).toBe(hidden)
    expect(workspaceReducer(hidden, { type: 'input_uncertain', event })).toBe(
      hidden,
    )
    expect(workspaceReducer(hidden, { type: 'admitted', event })).toBe(hidden)
    expect(Object.keys(hidden)).not.toContain('input')
  })

  it('keeps uncertain input paused when later output or GAP arrives', () => {
    const uncertain = workspaceReducer(connected(), {
      type: 'input_uncertain',
      event,
    })
    const gap = workspaceReducer(uncertain, {
      type: 'gap',
      event,
      fromCursor: '1',
      toCursor: '3',
    })
    expect(gap.status).toBe('input_uncertain')
    expect(gap.cursor).toBe('2')
    expect(
      workspaceReducer(gap, { type: 'output_observed', event, cursor: '4' })
        .status,
    ).toBe('input_uncertain')
  })

  it('does not replace an in-flight exact Stop with Start or a transport error', () => {
    const stopping = workspaceReducer(connected(), {
      type: 'stop_requested',
      attempt: '3',
    })
    const error = workspaceReducer(stopping, {
      type: 'error',
      event,
      message: 'transport closed',
    })
    expect(error.status).toBe('stopping')
    expect(
      workspaceReducer(error, {
        type: 'start_requested',
        projectId,
        attempt: '4',
      }),
    ).toBe(error)
    expect(
      workspaceReducer(error, { type: 'stopped', attempt: '3', fence }).status,
    ).toBe('stopped')
  })

  it('requires exact Stop response correlation and never revives a stopped process', () => {
    const stopping = workspaceReducer(connected(), {
      type: 'stop_requested',
      attempt: '3',
    })
    expect(
      workspaceReducer(stopping, { type: 'stopped', attempt: '2', fence }),
    ).toBe(stopping)
    const state = stopped()
    expect(state.status).toBe('stopped')
    const actions: WorkspaceAction[] = [
      { type: 'checking' },
      { type: 'connecting', attempt: '4' },
      { type: 'reconnect_requested', attempt: '4' },
      { type: 'stop_requested', attempt: '4' },
      { type: 'attachment_prepared', attempt: '2', event },
      { type: 'admitted', event },
      { type: 'detached', event },
      { type: 'input_uncertain', event },
      { type: 'gap', event, fromCursor: '1', toCursor: '3' },
      { type: 'error', event, message: 'late' },
      { type: 'exited', event, message: 'late' },
      {
        type: 'runtime_restarted',
        previous: fence,
        next: { ...fence, runtimeEpoch: '5' },
      },
      {
        type: 'api_restarted',
        previous: fence,
        next: { ...fence, apiAuthorityEpoch: '3' },
      },
      { type: 'visibility_changed', visible: false },
    ]
    for (const action of actions)
      expect(workspaceReducer(state, action)).toBe(state)
    expect(
      workspaceReducer(state, {
        type: 'start_requested',
        projectId,
        attempt: '4',
      }).status,
    ).toBe('starting')
  })
})
