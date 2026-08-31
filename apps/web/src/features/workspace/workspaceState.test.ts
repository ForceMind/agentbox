import { describe, expect, it } from 'vitest'

import {
  initialWorkspaceState,
  workspaceReducer,
  WorkspaceState,
} from './workspaceState'

describe('workspaceReducer', () => {
  it('does not infer connected from a start response', () => {
    const starting = workspaceReducer(initialWorkspaceState, {
      type: 'start_requested',
      projectId: 'prj_0123456789abcdef0123456789abcdef',
    })
    const connecting = workspaceReducer(starting, {
      type: 'start_accepted',
      projectId: starting.projectId!,
      workspaceId: 'aws_0123456789abcdef0123456789abcdef',
    })

    expect(starting.status).toBe('starting')
    expect(connecting.status).toBe('connecting')
    expect(workspaceReducer(connecting, { type: 'admitted' }).status).toBe(
      'connected',
    )
  })

  it('ignores an admission event outside the connecting states', () => {
    expect(workspaceReducer(initialWorkspaceState, { type: 'admitted' })).toBe(
      initialWorkspaceState,
    )
  })

  it.each<WorkspaceState['status']>([
    'checking',
    'starting',
    'connecting',
    'connected',
    'reconnecting',
    'error',
    'stopping',
    'detached',
    'stopped',
    'gap',
    'input_uncertain',
    'login_required',
    'trust_required',
    'exited',
    'missing',
    'collision',
    'unavailable',
  ])('represents the %s state without collapsing it', (status) => {
    const next =
      status === 'checking'
        ? workspaceReducer(initialWorkspaceState, { type: 'checking' })
        : status === 'starting'
          ? workspaceReducer(initialWorkspaceState, {
              type: 'start_requested',
              projectId: 'prj_0123456789abcdef0123456789abcdef',
            })
          : status === 'connecting'
            ? workspaceReducer(initialWorkspaceState, { type: 'connecting' })
            : status === 'reconnecting'
              ? workspaceReducer(initialWorkspaceState, {
                  type: 'reconnect_requested',
                })
              : status === 'stopping'
                ? workspaceReducer(initialWorkspaceState, {
                    type: 'stop_requested',
                  })
                : status === 'stopped'
                  ? workspaceReducer(initialWorkspaceState, { type: 'stopped' })
                  : status === 'detached'
                    ? workspaceReducer(initialWorkspaceState, {
                        type: 'detached',
                      })
                    : status === 'gap'
                      ? workspaceReducer(initialWorkspaceState, { type: 'gap' })
                      : status === 'input_uncertain'
                        ? workspaceReducer(initialWorkspaceState, {
                            type: 'input_uncertain',
                          })
                        : status === 'connected'
                          ? workspaceReducer(
                              workspaceReducer(initialWorkspaceState, {
                                type: 'connecting',
                              }),
                              { type: 'admitted' },
                            )
                          : workspaceReducer(initialWorkspaceState, {
                              type: status,
                              message: 'fixture',
                            })

    expect(next.status).toBe(status)
  })
})
