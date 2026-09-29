import { describe, expect, it } from 'vitest'

import {
  parseNavigationLabelDeleteImpactResponse,
  parseNavigationLabelListResponse,
  parseNavigationLabelResponse,
  parseProjectLabelSetResponse,
  parseWorkspaceLabelSetResponse,
} from '../../lib/contracts'

const projectId = `prj_${'a'.repeat(32)}`
const labelId = `lbl_${'b'.repeat(32)}`
const label = {
  id: labelId,
  name: 'Team Review',
  color: 'sky',
  revision: 1,
  updated_at: '2026-09-29T00:00:00Z',
}

function envelope(data: object) {
  return { api_version: 'v1', request_id: 'req_labels', data }
}

describe('Navigation label Web contract', () => {
  it('accepts exact bounded catalog and empty/nonempty Project revisions', () => {
    const catalog = parseNavigationLabelListResponse(
      envelope({ labels: [label] }),
    )
    expect(catalog.data.labels[0]?.id).toBe(labelId)
    expect(parseNavigationLabelResponse(envelope(label)).data.color).toBe('sky')
    const empty = parseProjectLabelSetResponse(
      envelope({
        project_id: projectId,
        labels: [],
        revision: 0,
        updated_at: null,
      }),
    )
    expect(empty.data.labels).toEqual([])
    const assigned = parseProjectLabelSetResponse(
      envelope({
        project_id: projectId,
        labels: [label],
        revision: 1,
        updated_at: '2026-09-29T00:00:00Z',
      }),
    )
    expect(assigned.data.labels[0]?.name).toBe('Team Review')
    expect(
      parseNavigationLabelDeleteImpactResponse(
        envelope({
          label_id: labelId,
          affected_project_count: 1,
          affected_workspace_count: 0,
        }),
      ).data.affected_project_count,
    ).toBe(1)
    expect(
      parseWorkspaceLabelSetResponse(
        envelope({
          workspace_id: `aws_${'c'.repeat(32)}`,
          project_id: projectId,
          agent_type: 'codex',
          labels: [label],
          revision: 1,
          updated_at: '2026-09-29T00:00:00Z',
        }),
      ).data.labels[0]?.id,
    ).toBe(labelId)
  })

  it('rejects stale or malformed authority and display metadata', () => {
    for (const bad of [
      { ...label, id: '../../settings' },
      { ...label, color: 'script' },
      { ...label, name: 'a\u202eb' },
      { ...label, name: 'Team  Review' },
      { ...label, revision: 2 ** 53 },
      { ...label, updated_at: 'yesterday' },
      { ...label, path: '/etc/passwd' },
    ]) {
      expect(() => parseNavigationLabelResponse(envelope(bad))).toThrow()
    }
    expect(() =>
      parseNavigationLabelListResponse(envelope({ labels: [label, label] })),
    ).toThrow()
    expect(() =>
      parseProjectLabelSetResponse(
        envelope({
          project_id: projectId,
          labels: [label],
          revision: 0,
          updated_at: null,
        }),
      ),
    ).toThrow()
    expect(() =>
      parseNavigationLabelDeleteImpactResponse(
        envelope({
          label_id: labelId,
          affected_project_count: 10_001,
          affected_workspace_count: 0,
        }),
      ),
    ).toThrow()
  })
})
