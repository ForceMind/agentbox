import { describe, expect, it } from 'vitest'

import {
  parseProjectFavoriteListResponse,
  parseProjectFavoriteResponse,
} from '../../lib/contracts'

const projectId = `prj_${'a'.repeat(32)}`
const saved = {
  project_id: projectId,
  favorite: true,
  revision: 1,
  updated_at: '2026-09-29T00:00:00Z',
}
const envelope = (data: unknown) => ({
  api_version: 'v1',
  request_id: 'req_favorite',
  data,
})

describe('Project favorite Web contract', () => {
  it('accepts absent and saved revisions with exact fields', () => {
    expect(
      parseProjectFavoriteResponse(
        envelope({
          project_id: projectId,
          favorite: false,
          revision: 0,
          updated_at: null,
        }),
      ).data.revision,
    ).toBe(0)
    expect(
      parseProjectFavoriteListResponse(envelope({ favorites: [saved] })).data
        .favorites,
    ).toEqual([saved])
  })

  it.each([
    { ...saved, path: '/etc/passwd' },
    { ...saved, project_id: '../escape' },
    { ...saved, revision: Number.MAX_SAFE_INTEGER + 1 },
    { ...saved, updated_at: '2026-02-30T00:00:00Z' },
    { ...saved, updated_at: null },
    { ...saved, favorite: 'true' },
    { ...saved, revision: 0 },
  ])('rejects malformed favorite rows', (invalid) => {
    expect(() => parseProjectFavoriteResponse(envelope(invalid))).toThrow()
  })

  it('rejects duplicate IDs, extra list fields and extra envelope fields', () => {
    expect(() =>
      parseProjectFavoriteListResponse(envelope({ favorites: [saved, saved] })),
    ).toThrow()
    expect(() =>
      parseProjectFavoriteListResponse(
        envelope({ favorites: [], path: '/etc' }),
      ),
    ).toThrow()
    expect(() =>
      parseProjectFavoriteListResponse({
        ...envelope({ favorites: [] }),
        secret: 1,
      }),
    ).toThrow()
  })
})
