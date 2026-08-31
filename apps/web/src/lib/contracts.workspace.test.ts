import { describe, expect, it } from 'vitest'

import { parseWorkspaceRuntimeStatusResponse } from './contracts'

const payload = {
  request_id: 'req_workspace_status',
  data: {
    workspace_id: 'aws_0123456789abcdef0123456789abcdef',
    project_id: 'prj_0123456789abcdef0123456789abcdef',
    agent_type: 'claude',
    generation: '1',
    binding_revision: '1',
    binding_digest: 'a'.repeat(64),
    state: 'RUNNING',
    reconciliation_state: 'authoritative',
    runtime_epoch: '2',
    process_state: 'RUNNING',
    exit_code: null,
    attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
  },
}

describe('Workspace runtime status contract', () => {
  it('parses bounded metadata without treating it as admission', () => {
    const result = parseWorkspaceRuntimeStatusResponse(payload)
    expect(result.data.workspace_id).toBe(payload.data.workspace_id)
    expect(result.data.attachment_capacity.limit).toBe('32')
  })

  it.each(['terminal', 'terminal_output', 'ticket'])(
    'rejects %s data',
    (key) => {
      expect(() =>
        parseWorkspaceRuntimeStatusResponse({
          ...payload,
          data: { ...payload.data, [key]: 'forbidden' },
        }),
      ).toThrow()
    },
  )
})
