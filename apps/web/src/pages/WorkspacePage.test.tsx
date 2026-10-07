import { fireEvent, render, screen, within } from '@testing-library/react'
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

vi.mock('../features/workspace/WorkspaceLabelsPanel', () => ({
  WorkspaceLabelsPanel: () => null,
}))

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
function loadedRuntime(receivedAt: number): WorkspacePageModel['runtimeView'] {
  return {
    status: 'loaded',
    receivedAt,
    observationToken: 3,
    response: {
      request_id: 'wreq_status',
      data: {
        workspace_id: 'aws_0123456789abcdef0123456789abcdef',
        project_id: project.id,
        agent_type: 'claude',
        generation: '7',
        binding_revision: '1',
        binding_digest: 'a'.repeat(64),
        state: 'RUNNING',
        reconciliation_state: 'authoritative',
        runtime_epoch: '9',
        process_state: 'RUNNING',
        exit_code: null,
        attachment_capacity: { admitted: '0', pending: '0', limit: '1' },
      },
    },
  }
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
    const projectSelect = screen.getByRole('combobox', {
      name: 'Formal READY Project',
    })
    if (_name === 'loading') {
      expect(projectSelect).toBeDisabled()
      expect(projectSelect).toHaveDisplayValue('Loading Projects…')
    } else if (_name === 'empty') {
      expect(projectSelect).toBeDisabled()
      expect(projectSelect).toHaveDisplayValue('No READY Projects')
    } else if (_name === 'unregistered') {
      expect(
        screen.getByText(
          'This AgentType is not registered and cannot start a workspace.',
        ),
      ).toBeVisible()
      expect(
        screen.getByRole('button', { name: 'Start workspace' }),
      ).toBeDisabled()
    } else {
      expect(
        screen.getByText(
          'The Project list is temporarily unavailable. Refresh and try again.',
        ),
      ).toBeVisible()
      expect(screen.getByText('CONTROL_PLANE_UNAVAILABLE')).toBeVisible()
      expect(
        screen.getByText('Workspace information is temporarily unavailable.'),
      ).toBeVisible()
    }
  })

  it('shows workspace lookup progress separately from Project loading', () => {
    render(<WorkspacePage model={model({ lookup: 'loading' })} />)
    expect(screen.getByText('Loading workspace information…')).toBeVisible()
    expect(
      screen.getByRole('combobox', { name: 'Formal READY Project' }),
    ).toBeEnabled()
    expect(
      screen.getByRole('button', { name: 'Connect terminal' }),
    ).toBeDisabled()
  })

  it('keeps the terminal nodes and uncontrolled input through rerenders and metadata disclosure changes', () => {
    const m = model({
      canInput: true,
      runtimeView: loadedRuntime(Date.parse('2026-10-07T08:00:00Z')),
    })
    const { container, rerender, unmount } = render(<WorkspacePage model={m} />)
    const viewport = container.querySelector('.workspace-terminal-frame')!
    const surface = screen.getByRole('log', { name: 'Controlled terminal' })
    const input = screen.getByRole('textbox', { name: 'Send input' })
    const rendererChild = document.createElement('span')
    surface.append(rendererChild)
    fireEvent.change(input, { target: { value: 'unsubmitted input' } })

    const summary = screen.getByText('Runtime metadata', {
      selector: 'summary',
    })
    const details = summary.closest('details')!
    expect(details).not.toHaveAttribute('open')
    fireEvent.click(summary)
    expect(details).toHaveAttribute('open')
    expect(screen.getByText('Process status')).toBeVisible()

    rerender(<WorkspacePage model={{ ...m, notice: 'START_CONFIRMED' }} />)
    fireEvent.click(summary)
    expect(details).not.toHaveAttribute('open')
    fireEvent(window, new Event('resize'))
    currentLocaleMock.mockReturnValue('zh-CN')
    rerender(<WorkspacePage model={{ ...m, pending: 'start' }} />)
    rerender(
      <WorkspacePage
        model={{ ...m, runtimeView: { status: 'stale', receivedAt: null } }}
      />,
    )
    expect(screen.queryByText('Runtime 元数据')).not.toBeInTheDocument()

    expect(
      container.querySelectorAll('.workspace-terminal-frame'),
    ).toHaveLength(1)
    expect(
      container.querySelectorAll('.workspace-terminal-surface'),
    ).toHaveLength(1)
    expect(container.querySelector('.workspace-terminal-frame')).toBe(viewport)
    expect(screen.getByRole('log', { name: '受控终端' })).toBe(surface)
    expect(surface.firstChild).toBe(rendererChild)
    expect(screen.getByRole('textbox', { name: '发送输入' })).toBe(input)
    expect(input).toHaveValue('unsubmitted input')
    expect(m.setTerminalViewport).toHaveBeenCalledExactlyOnceWith(viewport)
    expect(m.setTerminalSurface).toHaveBeenCalledExactlyOnceWith(surface)
    expect(m.setTerminalInputClearer).toHaveBeenCalledTimes(1)

    unmount()
    expect(m.setTerminalViewport).toHaveBeenCalledTimes(2)
    expect(m.setTerminalSurface).toHaveBeenCalledTimes(2)
    // React 19's development ref cleanup may append internal undefined arguments.
    expect(vi.mocked(m.setTerminalViewport).mock.calls.at(-1)?.[0]).toBeNull()
    expect(vi.mocked(m.setTerminalSurface).mock.calls.at(-1)?.[0]).toBeNull()
    expect(m.setTerminalInputClearer).toHaveBeenLastCalledWith(null)
  })

  const guardedActions = [
    ['canStart', 'Start workspace', 'start'],
    ['canStop', 'Stop workspace', 'requestStop'],
    ['canConnect', 'Connect terminal', 'connect'],
    ['canReconnect', 'Reconnect', 'reconnect'],
    ['canDetach', 'Disconnect', 'detach'],
    ['canInput', 'Send input', 'sendInput'],
  ] as const
  const pendingActions = [
    null,
    'start',
    'connect',
    'reconnect',
    'detach',
    'stop',
  ] as const

  it.each(
    guardedActions.flatMap(([permission, label, callback]) =>
      [false, true].flatMap((allowed) =>
        pendingActions.map((pending) => ({
          permission,
          label,
          callback,
          allowed,
          pending,
        })),
      ),
    ),
  )(
    'guards $label with $permission=$allowed and pending=$pending',
    ({ permission, label, callback, allowed, pending }) => {
      const m = model({ [permission]: allowed, pending })
      render(<WorkspacePage model={m} />)
      const button = screen.getByRole('button', { name: label })
      const enabled = allowed && pending === null
      if (enabled) expect(button).toBeEnabled()
      else expect(button).toBeDisabled()
      if (permission === 'canInput') {
        const input = screen.getByRole('textbox', { name: label })
        if (enabled) expect(input).toBeEnabled()
        else expect(input).toBeDisabled()
        fireEvent.change(input, { target: { value: 'bounded input' } })
        // A direct submit must obey the same guard as the disabled controls.
        fireEvent.submit(input.closest('form')!)
        if (enabled) expect(m.sendInput).toHaveBeenCalledWith('bounded input\r')
      } else {
        fireEvent.click(button)
      }
      expect(m[callback]).toHaveBeenCalledTimes(enabled ? 1 : 0)
    },
  )

  it('keeps a long Project name as inert isolated text in the selector and context', () => {
    const displayName = '<img src=x onerror=alert(1)> 中文 مشروع '.repeat(12)
    const { container } = render(
      <WorkspacePage
        model={model({ projects: [{ ...project, displayName }] })}
      />,
    )
    expect(container.querySelector('img')).toBeNull()
    const value = container.querySelector('.workspace-current-selection bdi')!
    expect(value.textContent).toBe(displayName)
    expect(value).toHaveAttribute('dir', 'auto')
    expect(value).toHaveAttribute('translate', 'no')
    expect(
      screen.getByRole('option', { name: displayName.trim() }),
    ).toHaveValue(project.id)
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
    expect(
      screen.getByText(
        'The managed browser trust provider is unavailable, so no terminal ticket was requested.',
      ),
    ).toBeVisible()
    expect(screen.getByText('ATTACHMENT_UNAVAILABLE')).toBeVisible()
    expect(
      screen.getByText(
        'Terminal content is not stored in browser storage or offered as a history download.',
      ),
    ).toBeVisible()
  })

  it('keeps identity and reconciliation evidence visible with Runtime details closed', () => {
    const runtimeView = loadedRuntime(Date.parse('2026-10-07T08:00:00Z'))
    if (runtimeView.status !== 'loaded')
      throw new Error('Expected loaded fixture')
    runtimeView.response.data.reconciliation_state = 'reconciliation_required'
    render(<WorkspacePage model={model({ runtimeView })} />)
    expect(
      screen.getByText('Runtime metadata').closest('details'),
    ).not.toHaveAttribute('open')
    expect(
      screen.getByText('aws_0123456789abcdef0123456789abcdef'),
    ).toBeVisible()
    expect(screen.getByText('reconciliation_required')).toBeVisible()
  })

  it.each<WorkspacePageModel['runtimeView']>([
    { status: 'idle' },
    { status: 'loading' },
    { status: 'stale', receivedAt: null },
    { status: 'revalidating', receivedAt: null },
    { status: 'error', error: { code: 'WAW_STATUS_UNAVAILABLE' } },
  ])(
    'omits empty Runtime details when the snapshot is $status',
    (runtimeView) => {
      render(<WorkspacePage model={model({ runtimeView })} />)
      expect(screen.queryByText('Runtime metadata')).not.toBeInTheDocument()
      expect(screen.getByText('Trust provider unavailable')).toBeVisible()
      expect(
        screen.getByRole('log', { name: 'Controlled terminal' }),
      ).toBeInTheDocument()
    },
  )

  it('shows bounded redraw and input outcomes without hiding the sensitive-output notice', () => {
    const m = model()
    const { rerender } = render(
      <WorkspacePage
        model={{
          ...m,
          attachment: { ...m.attachment, freshRedrawTruncated: true },
        }}
      />,
    )
    expect(
      screen.getByText(
        'The initial terminal redraw was bounded. Refreshing the terminal starts a new bounded redraw.',
      ),
    ).toBeVisible()
    for (const state of [
      'local_uncertain',
      'write_uncertain',
      'rejected',
    ] as const) {
      rerender(
        <WorkspacePage
          model={{
            ...m,
            attachment: {
              ...m.attachment,
              lastInputOutcome: { state, reasonCode: 'INPUT_WRITE_UNCERTAIN' },
            },
          }}
        />,
      )
      expect(
        screen.getByText('Input delivery is uncertain and will not be resent.'),
      ).toBeVisible()
      expect(screen.getByText('INPUT_WRITE_UNCERTAIN')).toBeVisible()
      expect(
        screen.getByText(
          'Terminal content is not stored in browser storage or offered as a history download.',
        ),
      ).toBeVisible()
    }
    expect(m.sendInput).not.toHaveBeenCalled()
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

  it('shows the client receive time only for a current loaded snapshot', () => {
    const receivedAt = Date.parse('2026-09-06T10:11:12.000Z')
    const { container, rerender } = render(
      <WorkspacePage
        model={model({ runtimeView: loadedRuntime(receivedAt) })}
      />,
    )
    const time = container.querySelector('time')
    expect(time).not.toBeNull()
    expect(time).toHaveAttribute('dateTime', '2026-09-06T10:11:12.000Z')
    expect(time?.textContent).not.toBe('')
    expect(screen.getByText('Status received')).toBeVisible()

    rerender(
      <WorkspacePage
        model={model({
          runtimeView: { status: 'stale', receivedAt },
          canStart: false,
          canStop: false,
        })}
      />,
    )
    expect(container.querySelector('time')).toBeNull()
    expect(screen.queryByText('Runtime metadata')).not.toBeInTheDocument()
    expect(
      screen.getByText(
        'The previous Runtime snapshot is no longer current. Workspace actions are paused.',
      ),
    ).toBeVisible()
  })

  it('renders revalidation as a local paused state without Runtime data', () => {
    render(
      <WorkspacePage
        model={model({
          runtimeView: {
            status: 'revalidating',
            receivedAt: Date.parse('2026-09-06T10:11:12.000Z'),
          },
          canStart: false,
          canStop: false,
        })}
      />,
    )

    expect(
      screen.getByText(
        'Reconfirming the current Runtime status. Workspace actions remain paused.',
      ),
    ).toBeVisible()
    expect(screen.queryByText('Status received')).not.toBeInTheDocument()
    expect(screen.queryByText('Runtime metadata')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Refresh workspace status' }),
    ).toBeDisabled()
    expect(
      screen.queryByText('unsafe server status prose'),
    ).not.toBeInTheDocument()
  })

  it('localizes the stale snapshot state in Chinese', () => {
    currentLocaleMock.mockReturnValue('zh-CN')
    render(
      <WorkspacePage
        model={model({
          runtimeView: { status: 'stale', receivedAt: null },
          canStart: false,
          canStop: false,
        })}
      />,
    )

    expect(
      screen.getByText('之前的 Runtime 快照已失效，工作区操作已暂停。'),
    ).toBeVisible()
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

  it.each(['start', 'connect', 'reconnect', 'detach', 'stop'] as const)(
    'prevents Stop dismissal and repeated confirmation while %s is pending',
    (pending) => {
      const stopTarget = {
        workspaceId: 'aws_abcdef0123456789abcdef0123456789',
        generation: '19',
      }
      const m = model({ stopTarget })
      const { rerender } = render(<WorkspacePage model={m} />)
      const dialog = screen.getByRole('dialog', {
        name: 'Confirm workspace stop',
      })
      // The confirmation target comes from the captured exact target, not the record.
      expect(dialog).toHaveTextContent(stopTarget.workspaceId)
      expect(dialog).toHaveTextContent('Generation: 19')
      expect(dialog).not.toHaveTextContent(m.workspaceId!)
      fireEvent.click(
        within(dialog).getByRole('button', { name: 'Confirm stop' }),
      )
      expect(m.confirmStop).toHaveBeenCalledTimes(1)

      rerender(<WorkspacePage model={{ ...m, pending }} />)
      const cancel = within(dialog).getByRole('button', { name: 'Cancel' })
      const confirm = within(dialog).getByRole('button', {
        name: 'Confirm stop',
      })
      expect(cancel).toBeDisabled()
      expect(confirm).toBeDisabled()
      fireEvent.click(confirm)
      fireEvent.click(confirm)
      fireEvent.click(cancel)
      const escape = new Event('cancel', { cancelable: true })
      fireEvent(dialog, escape)
      expect(escape.defaultPrevented).toBe(true)
      expect(dialog).toHaveAttribute('open')
      expect(m.confirmStop).toHaveBeenCalledTimes(1)
      expect(m.cancelStop).not.toHaveBeenCalled()

      rerender(<WorkspacePage model={m} />)
      const idleEscape = new Event('cancel', { cancelable: true })
      fireEvent(dialog, idleEscape)
      expect(idleEscape.defaultPrevented).toBe(true)
      expect(m.cancelStop).toHaveBeenCalledTimes(1)
      rerender(<WorkspacePage model={{ ...m, stopTarget: null }} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(confirm).toBeDisabled()
      fireEvent.click(confirm)
      expect(m.confirmStop).toHaveBeenCalledTimes(1)
    },
  )

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
