import { fireEvent, render, screen } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { WorkspacePage } from './WorkspacePage'
import type { WorkspacePageModel } from '../features/workspace/workspaceView'

// jsdom has no native dialog implementation; browser E2E verifies modal focus.
const originalShowModal = HTMLDialogElement.prototype.showModal
const originalClose = HTMLDialogElement.prototype.close
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value(this: HTMLDialogElement) {
      this.setAttribute('open', '')
    },
  })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value(this: HTMLDialogElement) {
      this.removeAttribute('open')
    },
  })
})
afterAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value: originalShowModal,
  })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value: originalClose,
  })
})

const project = {
  id: 'prj_0123456789abcdef0123456789abcdef',
  displayName: 'Demo Project',
}
function model(
  overrides: Partial<WorkspacePageModel> = {},
): WorkspacePageModel {
  return {
    projects: [project],
    projectsLoading: false,
    projectError: null,
    selectedProjectId: project.id,
    agentType: 'claude',
    lookup: 'ready',
    workspaceId: 'aws_0123456789abcdef0123456789abcdef',
    generation: '7',
    lifecycleState: 'RUNNING',
    reconciliationState: 'authoritative',
    runtimeView: { status: 'idle' },
    pending: null,
    error: null,
    notice: null,
    canStart: false,
    canStop: true,
    stopTarget: null,
    selectProject: vi.fn(),
    selectAgent: vi.fn(),
    refresh: vi.fn(async () => undefined),
    start: vi.fn(async () => undefined),
    requestStop: vi.fn(),
    cancelStop: vi.fn(),
    confirmStop: vi.fn(async () => undefined),
    ...overrides,
  }
}

describe('WorkspacePage', () => {
  it('selects project and agent and keeps RUNNING unadmitted', async () => {
    const m = model({
      projects: [
        project,
        { id: 'prj_abcdef0123456789abcdef0123456789', displayName: 'Other' },
      ],
    })
    render(<WorkspacePage model={m} />)
    fireEvent.change(screen.getByLabelText('正式 READY Project'), {
      target: { value: 'prj_abcdef0123456789abcdef0123456789' },
    })
    fireEvent.change(screen.getByLabelText('AgentType'), {
      target: { value: 'codex' },
    })
    expect(m.selectProject).toHaveBeenCalledWith(
      'prj_abcdef0123456789abcdef0123456789',
    )
    expect(m.selectAgent).toHaveBeenCalledWith('codex')
    expect(screen.getByText('NOT ADMITTED')).toBeInTheDocument()
  })

  it.each([
    ['loading', { projectsLoading: true, projects: [] }],
    ['empty', { projects: [] }],
    ['unregistered', { lookup: 'unregistered' as const }],
    ['error', { lookup: 'error' as const, projectError: 'Project 加载失败' }],
  ])('renders %s state', (_name, overrides) => {
    render(<WorkspacePage model={model(overrides)} />)
    expect(
      screen.getByRole('heading', { name: '交互式工作区' }),
    ).toBeInTheDocument()
  })

  it('applies Start enabled rule and pending disables it', async () => {
    const m = model({
      pending: 'start',
      canStart: true,
      canStop: false,
      lifecycleState: 'STARTING',
    })
    render(<WorkspacePage model={m} />)
    expect(screen.getByRole('button', { name: '启动工作区' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '连接终端' })).toBeDisabled()
  })

  it('requires exact Stop confirmation and supports cancel', async () => {
    const m = model()
    const { rerender } = render(<WorkspacePage model={m} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '停止工作区' }))
    expect(m.requestStop).toHaveBeenCalledTimes(1)
    const stopTarget = {
      workspaceId: 'aws_0123456789abcdef0123456789abcdef',
      generation: '7',
    }
    rerender(<WorkspacePage model={{ ...m, stopTarget }} />)
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'aws_0123456789abcdef0123456789abcdef',
    )
    expect(screen.getByRole('dialog')).toHaveTextContent('Generation：7')
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(m.cancelStop).toHaveBeenCalledTimes(1)
    rerender(<WorkspacePage model={m} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '停止工作区' }))
    rerender(<WorkspacePage model={{ ...m, stopTarget }} />)
    fireEvent.click(screen.getByRole('button', { name: '确认停止' }))
    expect(m.confirmStop).toHaveBeenCalledTimes(1)
    expect(window.localStorage).toHaveLength(0)
    expect(window.sessionStorage).toHaveLength(0)
  })
})
