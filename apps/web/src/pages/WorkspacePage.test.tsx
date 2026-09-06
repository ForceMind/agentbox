import { fireEvent, render, screen } from '@testing-library/react'
import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'

const currentLocaleMock = vi.hoisted(() => vi.fn((): 'en' | 'zh-CN' => 'en'))

vi.mock('../i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../i18n')>()
  return { ...actual, currentLocale: currentLocaleMock }
})

import { WorkspacePage } from './WorkspacePage'
import { MAX_INPUT_BYTES } from '../features/workspace/wawCryptoProfile'
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
beforeEach(() => currentLocaleMock.mockReturnValue('en'))

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
    attachment: {
      status: 'UNAVAILABLE',
      reason: 'ATTACHMENT_UNAVAILABLE',
      outputCursor: null,
      freshRedrawTruncated: false,
      input: null,
      lastInputOutcome: null,
      attached: null,
      providerAvailable: false,
      surfaceReady: true,
    },
    pending: null,
    error: null,
    notice: null,
    canStart: false,
    canStop: true,
    canConnect: false,
    canReconnect: false,
    canDetach: false,
    canInput: false,
    canResize: false,
    stopTarget: null,
    selectProject: vi.fn(),
    selectAgent: vi.fn(),
    refresh: vi.fn(async () => undefined),
    start: vi.fn(async () => undefined),
    requestStop: vi.fn(),
    cancelStop: vi.fn(),
    confirmStop: vi.fn(async () => undefined),
    setTerminalSurface: vi.fn(),
    setTerminalViewport: vi.fn(),
    setTerminalInputClearer: vi.fn(),
    connect: vi.fn(async () => undefined),
    reconnect: vi.fn(async () => undefined),
    detach: vi.fn(async () => undefined),
    sendInput: vi.fn(async () => undefined),
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
    expect(screen.getByText('Trust provider unavailable')).toBeInTheDocument()
  })

  it.each([
    ['loading', { projectsLoading: true, projects: [] }],
    ['empty', { projects: [] }],
    ['unregistered', { lookup: 'unregistered' as const }],
    [
      'error',
      {
        lookup: 'error' as const,
        projectError: { code: 'CONTROL_PLANE_UNAVAILABLE' },
      },
    ],
  ])('renders %s state', (_name, overrides) => {
    render(<WorkspacePage model={model(overrides)} />)
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
    render(<WorkspacePage model={m} />)
    expect(
      screen.getByRole('button', { name: 'Start workspace' }),
    ).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Connect terminal' }),
    ).toBeDisabled()
  })

  it('binds the terminal surface and sends bounded terminal input with CR without persisting plaintext', async () => {
    const m = model({
      attachment: {
        status: 'CONNECTED',
        reason: null,
        outputCursor: '4',
        freshRedrawTruncated: false,
        input: null,
        lastInputOutcome: null,
        attached: null,
        providerAvailable: true,
        surfaceReady: true,
      },
      canConnect: false,
      canReconnect: false,
      canDetach: true,
      canInput: true,
      canResize: true,
    })
    render(<WorkspacePage model={m} />)
    expect(m.setTerminalSurface).toHaveBeenCalledWith(expect.any(HTMLElement))
    expect(m.setTerminalViewport).toHaveBeenCalledWith(expect.any(HTMLElement))
    fireEvent.click(screen.getByRole('button', { name: 'Disconnect' }))
    expect(m.detach).toHaveBeenCalledTimes(1)

    const input = screen.getByRole('textbox', { name: 'Send input' })
    fireEvent.change(input, { target: { value: 'clear synchronously' } })
    const clearInput = vi
      .mocked(m.setTerminalInputClearer)
      .mock.calls.at(-1)![0]!
    clearInput()
    expect(input).toHaveValue('')
    fireEvent.change(input, { target: { value: 'status' } })
    fireEvent.submit(input.closest('form')!)
    expect(m.sendInput).toHaveBeenCalledWith('status\r')
    expect(input).toHaveValue('')

    fireEvent.submit(input.closest('form')!)
    expect(m.sendInput).toHaveBeenLastCalledWith('\r')

    fireEvent.compositionStart(input)
    fireEvent.change(input, { target: { value: '正在输入' } })
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
    fireEvent.submit(input.closest('form')!)
    expect(m.sendInput).toHaveBeenCalledTimes(2)
    fireEvent.compositionEnd(input)
    fireEvent.submit(input.closest('form')!)
    expect(m.sendInput).toHaveBeenLastCalledWith('正在输入\r')
    expect(input).toHaveValue('')

    fireEvent.change(input, {
      target: { value: 'a'.repeat(MAX_INPUT_BYTES - 1) },
    })
    fireEvent.submit(input.closest('form')!)
    expect(m.sendInput).toHaveBeenLastCalledWith(
      `${'a'.repeat(MAX_INPUT_BYTES - 1)}\r`,
    )

    fireEvent.change(input, { target: { value: 'a'.repeat(MAX_INPUT_BYTES) } })
    fireEvent.submit(input.closest('form')!)
    expect(m.sendInput).toHaveBeenCalledTimes(4)
    expect(
      screen.getByText('Terminal input is limited to 16 KiB.'),
    ).toBeVisible()
    expect(input).toHaveValue('a'.repeat(MAX_INPUT_BYTES))

    fireEvent.change(input, {
      target: { value: '界'.repeat(Math.ceil(MAX_INPUT_BYTES / 3)) },
    })
    fireEvent.submit(input.closest('form')!)
    expect(m.sendInput).toHaveBeenCalledTimes(4)

    fireEvent.paste(input, {
      clipboardData: { getData: () => 'one\ntwo' },
    })
    expect(
      screen.getByText('Multi-line paste is not sent through this input.'),
    ).toBeVisible()
    expect(m.sendInput).toHaveBeenCalledTimes(4)
    expect(screen.queryByLabelText('Columns')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Rows')).not.toBeInTheDocument()
    expect(
      screen.getByText('Terminal size follows the visible viewport.'),
    ).toBeVisible()
    expect(screen.queryByText('status')).not.toBeInTheDocument()
  })

  it('disables the input surface while an ACK is pending', () => {
    const m = model({
      attachment: {
        status: 'CONNECTED',
        reason: null,
        outputCursor: null,
        freshRedrawTruncated: false,
        input: {
          browserHop: '1',
          cryptoSequence: '1',
          state: 'published',
          reasonCode: null,
        },
        lastInputOutcome: null,
        attached: null,
        providerAvailable: true,
        surfaceReady: true,
      },
      canInput: false,
    })
    render(<WorkspacePage model={m} />)
    expect(screen.getByRole('textbox', { name: 'Send input' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Send input' })).toBeDisabled()
    expect(screen.getByText('Sending terminal input…')).toBeVisible()
  })

  it('does not enable Connect when the trust provider is unavailable', () => {
    const m = model()
    render(<WorkspacePage model={m} />)
    expect(screen.getByText('Trust provider unavailable')).toBeVisible()
    expect(
      screen.getByRole('button', { name: 'Connect terminal' }),
    ).toBeDisabled()
    expect(m.connect).not.toHaveBeenCalled()
  })

  it('localizes bounded input outcome metadata without rendering input plaintext', () => {
    const m = model({
      attachment: {
        status: 'CONNECTED',
        reason: null,
        outputCursor: null,
        freshRedrawTruncated: false,
        input: null,
        lastInputOutcome: {
          state: 'rejected',
          reasonCode: 'INPUT_RATE_LIMITED',
        },
        attached: null,
        providerAvailable: true,
        surfaceReady: true,
      },
    })
    const { rerender } = render(<WorkspacePage model={m} />)
    expect(
      screen.getByText('Input was rate limited and was not sent. Try again.'),
    ).toBeVisible()
    expect(screen.getByText('INPUT_RATE_LIMITED')).toBeVisible()
    expect(
      screen.queryByText('sensitive terminal input'),
    ).not.toBeInTheDocument()

    currentLocaleMock.mockReturnValue('zh-CN')
    rerender(
      <WorkspacePage
        model={{
          ...m,
          attachment: {
            ...m.attachment,
            lastInputOutcome: {
              state: 'write_uncertain',
              reasonCode: 'INPUT_WRITE_UNCERTAIN',
            },
          },
        }}
      />,
    )
    expect(screen.getByText('输入结果不确定，系统不会自动重发。')).toBeVisible()
  })

  it('keeps Runtime status failure code visible beside lifecycle actions', () => {
    render(
      <WorkspacePage
        model={model({
          runtimeView: {
            status: 'error',
            error: { code: 'WAW_STATUS_UNAVAILABLE' },
          },
        })}
      />,
    )
    expect(
      screen.getByText('Workspace status is temporarily unavailable.'),
    ).toBeVisible()
    expect(screen.getByText('WAW_STATUS_UNAVAILABLE')).toBeVisible()
  })

  it('requires exact Stop confirmation and supports cancel', async () => {
    const m = model()
    const { rerender } = render(<WorkspacePage model={m} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Stop workspace' }))
    expect(m.requestStop).toHaveBeenCalledTimes(1)
    const stopTarget = {
      workspaceId: 'aws_0123456789abcdef0123456789abcdef',
      generation: '7',
    }
    rerender(<WorkspacePage model={{ ...m, stopTarget }} />)
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'aws_0123456789abcdef0123456789abcdef',
    )
    expect(screen.getByRole('dialog')).toHaveTextContent('Generation: 7')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(m.cancelStop).toHaveBeenCalledTimes(1)
    rerender(<WorkspacePage model={m} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Stop workspace' }))
    rerender(<WorkspacePage model={{ ...m, stopTarget }} />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm stop' }))
    expect(m.confirmStop).toHaveBeenCalledTimes(1)
  })

  it('renders Chinese copy only for the zh-CN locale', () => {
    currentLocaleMock.mockReturnValue('zh-CN')
    render(<WorkspacePage model={model()} />)
    expect(screen.getByRole('heading', { name: '交互式工作区' })).toBeVisible()
    expect(screen.getByText('信任 provider 不可用')).toBeVisible()
    expect(screen.getByRole('button', { name: '启动工作区' })).toBeDisabled()
  })

  it('keeps technical values English and does not expose control-plane text', () => {
    render(
      <WorkspacePage
        model={model({
          projectError: {
            code: 'CONTROL_PLANE_UNAVAILABLE',
            requestId: 'req_workspace_project',
          },
          notice: 'START_CONFIRMED',
          error: { code: 'WAW_INVALID_AGENT' },
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
    const code = screen.getByText('WAW_INVALID_AGENT')
    expect(code).toHaveAttribute('lang', 'en')
    expect(code).toHaveAttribute('dir', 'ltr')
    expect(code).toHaveAttribute('translate', 'no')
  })

  it('maps recovery to a localized paused-operation notice', () => {
    currentLocaleMock.mockReturnValue('zh-CN')
    render(
      <WorkspacePage model={model({ notice: 'RUNTIME_RECOVERY_REQUIRED' })} />,
    )

    expect(
      screen.getByText('Runtime 需要恢复核对，工作区操作已暂停。'),
    ).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
