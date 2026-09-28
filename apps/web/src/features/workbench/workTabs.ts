// Adapted from getpaseo/paseo packages/app/src/screens/workspace/
// workspace-pane-state.ts at 30178c4f58b67f8472901356e1484022bd835de0
// (Apache-2.0). Copyright (c) 2025-present Mohamed Boudra.
// AgentBox keeps only bounded route identity, ordering and active fallback.

import { matchPath } from 'react-router-dom'

export type WorkTabKind = 'project' | 'changes' | 'workspace'

export type WorkTab = Readonly<{
  key: string
  projectId: string
  kind: WorkTabKind
  agentType: 'claude' | 'codex' | null
  href: string
}>

export const MAX_WORK_TABS = 12
const FORMAL_PROJECT_ID = /^prj_[0-9a-f]{32}$/

function projectId(value: string | undefined | null): string | null {
  return value && FORMAL_PROJECT_ID.test(value) ? value : null
}

export function workTabForLocation(
  pathname: string,
  search: string,
): WorkTab | null {
  const changes = matchPath('/projects/:projectId/changes', pathname)
  const changeProjectId = projectId(changes?.params.projectId)
  if (changeProjectId) {
    return {
      key: `changes:${changeProjectId}`,
      projectId: changeProjectId,
      kind: 'changes',
      agentType: null,
      href: `/projects/${changeProjectId}/changes`,
    }
  }
  const project = matchPath('/projects/:projectId', pathname)
  const detailProjectId = projectId(project?.params.projectId)
  if (detailProjectId) {
    return {
      key: `project:${detailProjectId}`,
      projectId: detailProjectId,
      kind: 'project',
      agentType: null,
      href: `/projects/${detailProjectId}`,
    }
  }
  if (
    pathname !== '/workspace' &&
    !matchPath('/workspace/:workspaceId', pathname)
  ) {
    return null
  }
  const params = new URLSearchParams(search)
  const workspaceProjectId = projectId(params.get('project_id'))
  const rawAgent = params.get('agent_type') ?? 'claude'
  if (!workspaceProjectId || (rawAgent !== 'claude' && rawAgent !== 'codex')) {
    return null
  }
  const agentType = rawAgent
  return {
    key: `workspace:${workspaceProjectId}:${agentType}`,
    projectId: workspaceProjectId,
    kind: 'workspace',
    agentType,
    // Always re-enter by formal Project/AgentType and let the existing
    // Workspace controller revalidate the current WAW row. A route handle is
    // not an attach, start, stop or content authority.
    href: `/workspace?project_id=${workspaceProjectId}&agent_type=${agentType}`,
  }
}

export function openWorkTab(
  tabs: readonly WorkTab[],
  requested: WorkTab,
): WorkTab[] {
  const existingIndex = tabs.findIndex((tab) => tab.key === requested.key)
  if (existingIndex >= 0) {
    return tabs.map((tab, index) => (index === existingIndex ? requested : tab))
  }
  return [...tabs.slice(-(MAX_WORK_TABS - 1)), requested]
}

export function closeWorkTab(
  tabs: readonly WorkTab[],
  key: string,
  activeKey: string | null,
): Readonly<{ tabs: WorkTab[]; nextHref: string | null }> {
  const index = tabs.findIndex((tab) => tab.key === key)
  if (index < 0) return { tabs: [...tabs], nextHref: null }
  const remaining = tabs.filter((tab) => tab.key !== key)
  if (key !== activeKey) return { tabs: remaining, nextHref: null }
  return {
    tabs: remaining,
    nextHref: (tabs[index + 1] ?? tabs[index - 1])?.href ?? '/projects',
  }
}
