import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../lib/api'
import type {
  CodexPairResponse,
  CodexStatusResponse,
} from '../../lib/contracts'
import {
  projectCodexError,
  projectCodexPair,
  projectCodexStatusResponse,
} from './useCodex'

function statusResponse(
  diagnostic: CodexStatusResponse['data']['diagnostics'][number],
): CodexStatusResponse {
  return {
    api_version: 'v1',
    request_id: 'req_codex_projection',
    data: {
      installed: true,
      version: '1.fixture',
      selected_executable: '/fixture/bin/codex',
      alternatives: [],
      installation_type: 'standalone',
      conflict_detected: false,
      authentication: 'authenticated',
      capabilities: {
        remote_control: 'supported',
        start: 'supported',
        stop: 'supported',
        pair: 'supported',
        status: 'unsupported',
      },
      remote_state: 'stopped',
      remote_confidence: 'reported',
      diagnostics: [diagnostic],
    },
  }
}

describe('Codex display projection', () => {
  it('does not read or retain diagnostic summary and remediation getters', () => {
    const summary = vi.fn(() => {
      throw new Error('diagnostic summary getter was read')
    })
    const remediation = vi.fn(() => {
      throw new Error('diagnostic remediation getter was read')
    })
    const diagnostic = {
      code: 'CODEX_REMOTE_STATUS_UNSUPPORTED',
      severity: 'info' as const,
      get summary(): string {
        return summary()
      },
      get remediation(): string | null {
        return remediation()
      },
    }

    const projected = projectCodexStatusResponse(statusResponse(diagnostic))

    expect(projected.data.diagnostics).toEqual([
      { code: 'CODEX_REMOTE_STATUS_UNSUPPORTED', severity: 'info' },
    ])
    expect(summary).not.toHaveBeenCalled()
    expect(remediation).not.toHaveBeenCalled()
    expect(projected.data.diagnostics[0]).not.toHaveProperty('summary')
    expect(projected.data.diagnostics[0]).not.toHaveProperty('remediation')
  })

  it('discards ApiError server prose and keeps only stable evidence', () => {
    const canary = 'SERVER-PROSE-CANARY-CODEX-9F4K'
    const projected = projectCodexError(
      new ApiError({
        code: 'UNRECOGNIZED_CODE',
        message: canary,
        requestId: 'req_codex_canary',
        status: 503,
      }),
      'CODEX_ACTION_FAILED',
    )

    expect(projected).toEqual({
      code: 'UNRECOGNIZED_CODE',
      requestId: 'req_codex_canary',
    })
    expect(JSON.stringify(projected)).not.toContain(canary)
    expect(projected).not.toHaveProperty('message')
  })

  it('retains only Runtime-compatible Pair Code values in the view model', () => {
    const valid: CodexPairResponse['data'] = {
      pair_code: 'PAIR-CODE-FIXTURE-1234',
      expires_at: null,
      display_once: true,
    }
    expect(projectCodexPair(valid)).toEqual({
      pair_code: 'PAIR-CODE-FIXTURE-1234',
    })

    for (const pairCode of [
      '短码',
      'PAIR CODE WITH SPACE',
      'PAIR-CODE-\u0000',
      'P'.repeat(65),
    ]) {
      const projected = projectCodexPair({ ...valid, pair_code: pairCode })
      expect(projected).toBeNull()
      expect(JSON.stringify(projected)).not.toContain(pairCode)
    }
  })

  it('keeps printable ASCII versions and drops every other external value', () => {
    const diagnostic = {
      code: 'CODEX_REMOTE_STATUS_UNSUPPORTED',
      severity: 'info' as const,
      summary: 'ignored',
      remediation: null,
    }
    const valid = statusResponse(diagnostic)
    valid.data.version = 'codex-cli 1.2.3-rc.4'
    expect(projectCodexStatusResponse(valid).data.version).toBe(
      'codex-cli 1.2.3-rc.4',
    )

    const invalid = statusResponse(diagnostic)
    invalid.data.version = '服务端版本说明-CANARY'
    const projected = projectCodexStatusResponse(invalid)
    expect(projected.data.version).toBeNull()
    expect(JSON.stringify(projected)).not.toContain('服务端版本说明-CANARY')
  })
})
