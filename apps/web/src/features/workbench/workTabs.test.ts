import { describe, expect, it } from 'vitest'

import {
  MAX_WORK_TABS,
  closeWorkTab,
  openWorkTab,
  workTabForLocation,
} from './workTabs'

const first = `prj_${'a'.repeat(32)}`
const second = `prj_${'b'.repeat(32)}`

describe('Project work tab identity', () => {
  it('maps only formal Project routes and drops unrelated query material', () => {
    expect(workTabForLocation(`/projects/${first}`, '?secret=discard')).toEqual(
      {
        key: `project:${first}`,
        projectId: first,
        kind: 'project',
        agentType: null,
        href: `/projects/${first}`,
      },
    )
    expect(workTabForLocation(`/projects/${first}/changes`, '')?.key).toBe(
      `changes:${first}`,
    )
    expect(
      workTabForLocation(
        '/workspace/waw_untrusted-handle',
        `?project_id=${first}&agent_type=codex&secret=discard`,
      ),
    ).toEqual({
      key: `workspace:${first}:codex`,
      projectId: first,
      kind: 'workspace',
      agentType: 'codex',
      href: `/workspace?project_id=${first}&agent_type=codex`,
    })
    expect(
      workTabForLocation('/workspace', `?project_id=${first}`)?.agentType,
    ).toBe('claude')
    expect(workTabForLocation('/workspace', '?project_id=../escape')).toBeNull()
    expect(
      workTabForLocation('/workspace', `?project_id=${first}&agent_type=other`),
    ).toBeNull()
    expect(workTabForLocation('/projects/prj_fixture', '')).toBeNull()
    expect(workTabForLocation('/dashboard', '')).toBeNull()
  })

  it('deduplicates without reordering and limits navigation state', () => {
    const project = workTabForLocation(`/projects/${first}`, '')!
    const changes = workTabForLocation(`/projects/${first}/changes`, '')!
    const other = workTabForLocation(`/projects/${second}`, '')!
    expect(openWorkTab([project, changes], project)).toEqual([project, changes])
    expect(
      openWorkTab([project, changes], other).map((tab) => tab.key),
    ).toEqual([project.key, changes.key, other.key])
    let tabs = [project, changes]
    for (let index = 0; index < 20; index += 1) {
      const id = `prj_${index.toString(16).padStart(32, '0')}`
      tabs = openWorkTab(tabs, workTabForLocation(`/projects/${id}`, '')!)
    }
    expect(tabs).toHaveLength(MAX_WORK_TABS)
    expect(tabs.at(-1)?.projectId).toBe(
      `prj_${(19).toString(16).padStart(32, '0')}`,
    )
  })

  it('closes navigation only and chooses the adjacent active route', () => {
    const project = workTabForLocation(`/projects/${first}`, '')!
    const changes = workTabForLocation(`/projects/${first}/changes`, '')!
    const other = workTabForLocation(`/projects/${second}`, '')!
    expect(
      closeWorkTab([project, changes, other], changes.key, project.key),
    ).toEqual({
      tabs: [project, other],
      nextHref: null,
    })
    expect(
      closeWorkTab([project, changes, other], changes.key, changes.key),
    ).toEqual({
      tabs: [project, other],
      nextHref: other.href,
    })
    expect(closeWorkTab([project], project.key, project.key)).toEqual({
      tabs: [],
      nextHref: '/projects',
    })
  })
})
