import { describe, expect, it } from 'vitest'

import {
  parseWorkspaceAttachmentTicketResponse,
  parseWorkspaceStartResponse,
  parseWorkspaceStopResponse,
  parseWorkspaceRuntimeStatusResponse,
} from './contracts'

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

const lifecycle = {
  request_id: 'req_start',
  workspace_id: 'aws_0123456789abcdef0123456789abcdef',
  project_id: 'prj_0123456789abcdef0123456789abcdef',
  agent_type: 'codex',
  state: 'RUNNING',
  generation: '7',
}

describe('Workspace lifecycle identity contracts', () => {
  it('accepts Codex start and stop responses with exact context', () => {
    expect(
      parseWorkspaceStartResponse(lifecycle, {
        projectId: lifecycle.project_id,
        agentType: 'codex',
      }).agent_type,
    ).toBe('codex')
    expect(
      parseWorkspaceStopResponse(
        { ...lifecycle, stop_operation_id: 'wst_1' },
        {
          workspaceId: lifecycle.workspace_id,
          generation: '7',
          agentType: 'codex',
        },
      ).stop_operation_id,
    ).toBe('wst_1')
  })

  it('rejects unknown, cross-agent, mismatched identity, and extra fields', () => {
    expect(() =>
      parseWorkspaceStartResponse({ ...lifecycle, agent_type: 'other' }),
    ).toThrow()
    expect(() =>
      parseWorkspaceStartResponse(lifecycle, { agentType: 'claude' }),
    ).toThrow()
    expect(() =>
      parseWorkspaceStartResponse({ ...lifecycle, extra: true }),
    ).toThrow()
    expect(() =>
      parseWorkspaceStopResponse(
        { ...lifecycle, stop_operation_id: 'wst_1' },
        { generation: '8' },
      ),
    ).toThrow()
  })

  it('rejects extra fields in ticket responses', () => {
    const ticket = {
      protocol_version: 1,
      request_id: 'req_ticket',
      ticket: 'memory',
      workspace_id: lifecycle.workspace_id,
      project_id: lifecycle.project_id,
      agent_type: 'codex',
      attachment_id: 'att_0123456789abcdef0123456789abcdef',
      mode: 'writer',
      lease_number: '1',
      generation: '7',
      binding_revision: '1',
      binding_digest: 'a'.repeat(64),
      auth_epoch: '1',
      api_authority_epoch: '1',
      runtime_host_installation_id: 'rhi_1',
      runtime_host_installation_revision: '1',
      runtime_epoch: '1',
      expires_at: '2026-09-03T00:00:00Z',
    }
    expect(
      parseWorkspaceAttachmentTicketResponse(ticket, {
        workspaceId: lifecycle.workspace_id,
        agentType: 'codex',
      }).agent_type,
    ).toBe('codex')
    expect(() =>
      parseWorkspaceAttachmentTicketResponse({ ...ticket, argv: [] }),
    ).toThrow()
  })
})
