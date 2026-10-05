import {
  parseProjectListResponse,
  type ProjectListResponse,
} from '../../lib/contracts'

export const PROJECT_ID = /^prj_[0-9a-f]{32}$/

/** Fixed metadata-only endpoint: no reconciliation, Git or CLI observations. */
export function parseRecentProjectListResponse(
  value: unknown,
): ProjectListResponse {
  const response = parseProjectListResponse(value)
  if (response.data.projects.length > 6)
    throw new Error('Recent project list exceeds its bound')
  const ids = new Set<string>()
  for (const project of response.data.projects) {
    if (
      !PROJECT_ID.test(project.id) ||
      ids.has(project.id) ||
      project.state === 'archived' ||
      project.git !== null ||
      project.github !== null ||
      project.claude_state !== null ||
      !/(?:Z|[+-]\d{2}:\d{2})$/.test(project.updated_at) ||
      !Number.isFinite(Date.parse(project.updated_at))
    ) {
      throw new Error('Invalid recent project metadata')
    }
    ids.add(project.id)
  }
  return response
}
