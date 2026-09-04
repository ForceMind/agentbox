import { fireEvent, render, screen } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { WorkspacePage } from './WorkspacePage'
import type { WorkspacePageModel } from '../features/workspace/workspaceView'
import { ApiError } from '../lib/api'

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
    render(<WorkspacePage model={m} locale="en" />)
    fireEvent.change(screen.getByLabelText('Formal READY Project'), {
      target: { value: 'prj_abcdef0123456789abcdef0123456789' },
    })
    fireEvent.change(screen.getByLabelText('AgentType'), {
      target: { value: 'codex' },
    })
    expect(m.selectProject).toHaveBeenCalledWith(
      'prj_abcdef0123456789abcdef0123456789',
    )
    expect(m.selectAgent).toHaveBeenCalledWith('codex')
    expect(screen.getByText('Not admitted')).toBeInTheDocument()
  })

  it.each([
    ['loading', { projectsLoading: true, projects: [] }],
    ['empty', { projects: [] }],
    ['unregistered', { lookup: 'unregistered' as const }],
    ['error', { lookup: 'error' as const, projectError: 'Project 加载失败' }],
  ])('renders %s state', (_name, overrides) => {
    render(<WorkspacePage model={model(overrides)} locale="en" />)
    expect(
      screen.getByRole('heading', { name: 'Interactive workspace' }),
    ).toBeInTheDocument()
  })

  it('applies Start enabled rule and pending disables it', async () => {
    const m = model({
      pending: 'start',
      canStart: true,
      canStop: false,
      lifecycleState: 'STARTING',
    })
    render(<WorkspacePage model={m} locale="en" />)
    expect(
      screen.getByRole('button', { name: 'Start workspace' }),
    ).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Connect terminal' }),
    ).toBeDisabled()
  })

  it('requires exact Stop confirmation and supports cancel', async () => {
    const m = model()
    const { rerender } = render(<WorkspacePage model={m} locale="en" />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Stop workspace' }))
    expect(m.requestStop).toHaveBeenCalledTimes(1)
    const stopTarget = {
      workspaceId: 'aws_0123456789abcdef0123456789abcdef',
      generation: '7',
    }
    rerender(<WorkspacePage model={{ ...m, stopTarget }} locale="en" />)
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'aws_0123456789abcdef0123456789abcdef',
    )
    expect(screen.getByRole('dialog')).toHaveTextContent('Generation: 7')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(m.cancelStop).toHaveBeenCalledTimes(1)
    rerender(<WorkspacePage model={m} locale="en" />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Stop workspace' }))
    rerender(<WorkspacePage model={{ ...m, stopTarget }} locale="en" />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm stop' }))
    expect(m.confirmStop).toHaveBeenCalledTimes(1)
    expect(window.localStorage).toHaveLength(0)
    expect(window.sessionStorage).toHaveLength(0)
  })

  it('renders Chinese copy only for the zh-CN locale', () => {
    render(<WorkspacePage model={model()} locale="zh-CN" />)
    expect(screen.getByRole('heading', { name: '交互式工作区' })).toBeVisible()
    expect(screen.getByText('尚未准入')).toBeVisible()
    expect(screen.getByRole('button', { name: '启动工作区' })).toBeDisabled()
  })

  it('keeps technical values English and does not expose control-plane text', () => {
    render(
      <WorkspacePage
        locale="en"
        model={model({
          projectError: '项目列表含有不可信细节',
          notice: 'START_CONFIRMED',
          error: new ApiError({
            code: 'WAW_INVALID_AGENT',
            message: '不可信的控制面错误消息',
            status: 400,
          }),
        })}
      />,
    )

    expect(
      screen.getByText(
        'The Project list is temporarily unavailable. Refresh and try again.',
      ),
    ).toBeVisible()
    expect(
      screen.getByText(
        'The start request was confirmed. Process status and browser terminal connection status are shown separately.',
      ),
    ).toBeVisible()
    expect(screen.queryByText('项目列表含有不可信细节')).not.toBeInTheDocument()
    expect(screen.queryByText('不可信的控制面错误消息')).not.toBeInTheDocument()
    const code = screen.getByText('WAW_INVALID_AGENT')
    expect(code).toHaveAttribute('lang', 'en')
    expect(code).toHaveAttribute('dir', 'ltr')
    expect(code).toHaveAttribute('translate', 'no')
  })

  it('maps recovery to a localized paused-operation notice', () => {
    render(
      <WorkspacePage
        locale="zh-CN"
        model={model({ notice: 'RUNTIME_RECOVERY_REQUIRED' })}
      />,
    )

    expect(
      screen.getByText('Runtime 需要恢复核对，工作区操作已暂停。'),
    ).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
