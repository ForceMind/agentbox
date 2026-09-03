import type { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClient } from '../../lib/api'
import { AuthContext } from '../auth/AuthContext'
import { useWorkspaceController } from './useWorkspaceController'
import { parseWorkspaceList, type WorkspaceMetadata } from './workspaceMetadata'

const projectId = 'prj_' + '1'.repeat(32)
const otherProject = 'prj_' + '2'.repeat(32)
const workspaceId = 'aws_' + '3'.repeat(32)
const otherWorkspace = 'aws_' + '4'.repeat(32)
const date = '2026-09-03T00:00:00Z'
const auth = {
  user: { id: 'adm_test', username: 'test' },
  session: { id: 'ses_test', expires_at: date },
  csrf_token: 'csrf-fixture',
}
function project(id: string, state = 'ready') {
  return {
    id,
    state,
    display_name: id === projectId ? '主项目' : '第二项目',
    slug: id,
    source_type: 'existing',
    repository_url: null,
    default_branch: null,
    created_at: date,
    updated_at: date,
    git: null,
    github: null,
    claude_state: 'stopped',
  }
}
function metadata(
  id = workspaceId,
  project = projectId,
  state = 'STARTING',
): WorkspaceMetadata {
  return {
    id,
    project_id: project,
    agent_type: 'codex',
    generation: 7,
    revision: 1,
    state,
    reconciliation_state: 'authoritative',
    created_at: date,
    updated_at: date,
    last_seen_at: date,
    exit_code: null,
    failure_code: null,
  }
}
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status })
}
function list(row: WorkspaceMetadata | null) {
  return { request_id: 'req_list', data: { workspaces: row ? [row] : [] } }
}
function runtime(row: WorkspaceMetadata, generation = String(row.generation)) {
  return {
    request_id: 'req_status',
    data: {
      workspace_id: row.id,
      project_id: row.project_id,
      agent_type: row.agent_type,
      generation,
      binding_revision: '1',
      binding_digest: 'a'.repeat(64),
      state: row.state,
      reconciliation_state: 'authoritative',
      runtime_epoch: '9',
      process_state: row.state === 'RUNNING' ? 'RUNNING' : 'NOT_STARTED',
      exit_code: null,
      attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
    },
  }
}
function wrapper({ children }: { children: ReactNode }) {
  return (
    <AuthContext.Provider
      value={{
        api: client,
        auth,
        status: 'authenticated',
        login: async () => undefined,
        logout: async () => undefined,
        refresh: async () => auth,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
const client = new ApiClient()
function fixture(initial = 'STARTING') {
  const rows = [
    metadata(workspaceId, projectId, initial),
    metadata(otherWorkspace, otherProject, 'RUNNING'),
  ]
  const fetcher = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(input.toString(), 'http://testserver')
      if (url.pathname === '/api/v1/projects')
        return json({
          api_version: 'v1',
          request_id: 'req_projects',
          data: {
            projects: [
              project(projectId),
              project(otherProject),
              project('prj_' + '5'.repeat(32), 'archived'),
            ],
          },
        })
      if (url.pathname === '/api/v1/workspaces')
        return json(
          list(
            rows.find(
              (row) =>
                row.project_id === url.searchParams.get('project_id') &&
                row.agent_type === url.searchParams.get('agent_type'),
            ) ?? null,
          ),
        )
      const row = rows.find(
        (row) =>
          url.pathname.includes(row.id) ||
          url.pathname.includes(row.project_id),
      )
      if (!row) return json({ error: { code: 'NOT_FOUND' } }, 404)
      if (url.pathname.endsWith('/status')) return json(runtime(row))
      if (url.pathname.endsWith('/start')) {
        expect(init?.headers).toMatchObject({ 'X-CSRF-Token': auth.csrf_token })
        row.state = 'RUNNING'
        row.revision++
        return json({
          request_id: 'req_start',
          workspace_id: row.id,
          project_id: row.project_id,
          agent_type: row.agent_type,
          generation: String(row.generation),
          state: row.state,
        })
      }
      if (url.pathname.endsWith('/stop')) {
        expect(JSON.parse(String(init?.body))).toEqual({ generation: '7' })
        row.state = 'STOPPED'
        row.revision++
        return json({
          request_id: 'req_stop',
          workspace_id: row.id,
          project_id: row.project_id,
          agent_type: row.agent_type,
          generation: String(row.generation),
          stop_operation_id: 'wso_' + '6'.repeat(32),
          state: 'STOPPED',
        })
      }
      return json({ request_id: 'req_workspace', data: row })
    },
  )
  vi.stubGlobal('fetch', fetcher)
  return { rows, fetcher }
}
afterEach(() => vi.unstubAllGlobals())

describe('Workspace metadata controller', () => {
  it('rejects an unknown URL AgentType without silently starting Claude', async () => {
    const { fetcher } = fixture()
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'shell' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.lookup).toBe('error'))
    expect(result.current.error?.code).toBe('WAW_INVALID_AGENT')
    await act(async () => {
      await result.current.start()
    })
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(
      false,
    )
  })

  it('discards a late lookup after selecting another Project', async () => {
    const { fetcher } = fixture()
    const original = fetcher.getMockImplementation()!
    let release!: (response: Response) => void
    const delayed = new Promise<Response>((resolve) => {
      release = resolve
    })
    fetcher.mockImplementation((input, init) =>
      input.toString().includes(`/workspaces?project_id=${projectId}`)
        ? delayed
        : original(input, init),
    )
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'codex' }),
      { wrapper },
    )
    await waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) =>
          url.toString().includes(`/workspaces?project_id=${projectId}`),
        ),
      ).toBe(true),
    )
    act(() => result.current.selectProject(otherProject))
    await waitFor(() => expect(result.current.workspaceId).toBe(otherWorkspace))
    await act(async () => {
      release(json(list(metadata())))
      await delayed
    })
    expect(result.current.workspaceId).toBe(otherWorkspace)
    expect(result.current.error).toBeNull()
  })

  it('does not display an old Start result in the newly selected Project', async () => {
    const { fetcher, rows } = fixture()
    const original = fetcher.getMockImplementation()!
    let release!: (response: Response) => void
    const delayed = new Promise<Response>((resolve) => {
      release = resolve
    })
    fetcher.mockImplementation((input, init) =>
      input.toString().endsWith('/start') ? delayed : original(input, init),
    )
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'codex' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.canStart).toBe(true))
    let starting!: Promise<void>
    act(() => {
      starting = result.current.start()
    })
    act(() => result.current.selectProject(otherProject))
    await waitFor(() => expect(result.current.workspaceId).toBe(otherWorkspace))
    await act(async () => {
      release(
        json({
          request_id: 'req_late',
          workspace_id: rows[0].id,
          project_id: projectId,
          agent_type: 'codex',
          generation: '7',
          state: 'RUNNING',
        }),
      )
      await starting
    })
    expect(result.current.workspaceId).toBe(otherWorkspace)
    expect(result.current.notice).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('blocks operations when Runtime itself requires recovery', async () => {
    const { fetcher, rows } = fixture('RUNNING')
    const original = fetcher.getMockImplementation()!
    const observation = runtime(rows[0])
    observation.data.state = 'UNKNOWN'
    observation.data.reconciliation_state = 'reconciliation_required'
    fetcher.mockImplementation((input, init) =>
      input.toString().endsWith('/status')
        ? Promise.resolve(json(observation))
        : original(input, init),
    )
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'codex' }),
      { wrapper },
    )
    await waitFor(() =>
      expect(result.current.runtimeView.status).toBe('loaded'),
    )
    expect(result.current.canStart).toBe(false)
    expect(result.current.canStop).toBe(false)
    expect(result.current.notice).toContain('恢复核对')
  })

  it('uses only READY Projects and never starts or gets a ticket automatically', async () => {
    const { fetcher } = fixture()
    const { result } = renderHook(() => useWorkspaceController({}), { wrapper })
    await waitFor(() => expect(result.current.projectsLoading).toBe(false))
    expect(result.current.projects.map((item) => item.id)).toEqual([
      projectId,
      otherProject,
    ])
    expect(result.current.selectedProjectId).toBe('')
    expect(result.current.canStart).toBe(false)
    act(() => {
      result.current.selectProject(projectId)
      result.current.selectAgent('codex')
    })
    await waitFor(() => expect(result.current.lookup).toBe('ready'))
    expect(
      fetcher.mock.calls.some(([url]) =>
        url.toString().includes(`project_id=${projectId}&agent_type=codex`),
      ),
    ).toBe(true)
    expect(
      fetcher.mock.calls.filter(([, init]) => init?.method === 'POST'),
    ).toHaveLength(0)
  })
  it('starts a registered workspace and requires a separate exact Stop confirmation', async () => {
    const { fetcher } = fixture()
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'codex' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.canStart).toBe(true))
    await act(async () => {
      await result.current.start()
    })
    await waitFor(() => expect(result.current.lifecycleState).toBe('RUNNING'))
    await waitFor(() =>
      expect(result.current.runtimeView.status).toBe('loaded'),
    )
    expect(result.current.notice).toContain('启动请求已确认')
    act(() => result.current.requestStop())
    expect(result.current.stopTarget).toMatchObject({
      workspaceId,
      generation: '7',
    })
    expect(
      fetcher.mock.calls.filter(([url]) => url.toString().endsWith('/stop')),
    ).toHaveLength(0)
    act(() => result.current.cancelStop())
    expect(result.current.stopTarget).toBeNull()
    act(() => result.current.requestStop())
    await act(async () => {
      await result.current.confirmStop()
    })
    await waitFor(() => expect(result.current.lifecycleState).toBe('STOPPED'))
    expect(result.current.notice).toContain('Git 修改已保留')
    expect(
      fetcher.mock.calls.some(([url]) =>
        /attachments|reconnect/.test(url.toString()),
      ),
    ).toBe(false)
  })
  it('clears a Stop target when selection changes and rejects the captured old handler', async () => {
    const { fetcher } = fixture('RUNNING')
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'codex' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.canStop).toBe(true))
    act(() => result.current.requestStop())
    const oldConfirm = result.current.confirmStop
    act(() => result.current.selectProject(otherProject))
    await act(async () => {
      await oldConfirm()
    })
    await waitFor(() => expect(result.current.workspaceId).toBe(otherWorkspace))
    expect(result.current.stopTarget).toBeNull()
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(
      false,
    )
  })
  it('does not infer a missing binding from an unfiltered or mismatched response', async () => {
    const { fetcher } = fixture()
    const original = fetcher.getMockImplementation()!
    fetcher.mockImplementation((input, init) =>
      input.toString().includes('/workspaces?')
        ? Promise.resolve(json(list(metadata(otherWorkspace, otherProject))))
        : original(input, init),
    )
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'codex' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.lookup).toBe('error'))
    expect(result.current.canStart).toBe(false)
  })
  it('keeps an unregistered AgentType unavailable and sends no Start', async () => {
    const { fetcher } = fixture()
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'claude' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.lookup).toBe('unregistered'))
    await act(async () => {
      await result.current.start()
    })
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(
      false,
    )
  })
  it('blocks controls when Runtime reports a different generation', async () => {
    const { fetcher, rows } = fixture('RUNNING')
    const original = fetcher.getMockImplementation()!
    fetcher.mockImplementation((input, init) =>
      input.toString().endsWith('/status')
        ? Promise.resolve(json(runtime(rows[0], '8')))
        : original(input, init),
    )
    const { result } = renderHook(
      () => useWorkspaceController({ projectId, agentType: 'codex' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.runtimeView.status).toBe('error'))
    expect(result.current.canStop).toBe(false)
  })
  it('resolves a workspace deep link to the exact READY Project and AgentType', async () => {
    fixture('RUNNING')
    const { result } = renderHook(
      () => useWorkspaceController({ workspaceId }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.workspaceId).toBe(workspaceId))
    expect(result.current.selectedProjectId).toBe(projectId)
    expect(result.current.agentType).toBe('codex')
  })
  it('rejects unknown fields and unsafe numeric generation in metadata', () => {
    expect(() =>
      parseWorkspaceList(
        list({ ...metadata(), generation: Number.MAX_SAFE_INTEGER + 1 }),
        projectId,
        'codex',
      ),
    ).toThrow()
    expect(() =>
      parseWorkspaceList(
        { ...list(metadata()), ticket: 'no' },
        projectId,
        'codex',
      ),
    ).toThrow()
    expect(parseWorkspaceList(list(null), projectId, 'codex')).toBeNull()
  })
})
