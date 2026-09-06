import { act, renderHook } from '@testing-library/react'
import { StrictMode, type MutableRefObject } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type {
  WorkspaceAttachmentTicketResponse,
  WorkspaceDetachResponse,
  WorkspaceRuntimeStatus,
} from '../../lib/contracts'
import { ApiError } from '../../lib/api'
import {
  useWAWBrowserAttachment,
  type WAWAttachmentActions,
  type WAWAttachmentControllerPort,
  type WAWAttachmentDependencies,
} from './useWAWBrowserAttachment'
import type { WAWTrustProviderPort } from './wawTrustProvider'
import type {
  WAWBrowserAttachmentIdentity,
  WAWBrowserConnectRequest,
  WAWBrowserControllerOptions,
  WAWBrowserControllerSnapshot,
  WAWBrowserControlRequest,
  WAWBrowserDetachReceipt,
  WAWBrowserInputOutcome,
  WAWBrowserStopOutcome,
} from './wawBrowserController'

const projectId = `prj_${'1'.repeat(32)}`
const workspaceId = `aws_${'2'.repeat(32)}`
const runtime: WorkspaceRuntimeStatus = {
  workspace_id: workspaceId,
  project_id: projectId,
  agent_type: 'codex',
  generation: '7',
  binding_revision: '1',
  binding_digest: 'a'.repeat(64),
  state: 'RUNNING',
  reconciliation_state: 'authoritative',
  runtime_epoch: '9',
  process_state: 'RUNNING',
  exit_code: null,
  attachment_capacity: { admitted: '0', pending: '0', limit: '32' },
}

const ticket: WorkspaceAttachmentTicketResponse = {
  protocol_version: 1,
  request_id: `req_${'1'.repeat(32)}`,
  ticket: `wat_${'a'.repeat(32)}`,
  workspace_id: workspaceId,
  project_id: projectId,
  agent_type: 'codex',
  attachment_id: `att_${'3'.repeat(32)}`,
  mode: 'writer',
  lease_number: '4',
  generation: '7',
  binding_revision: '1',
  binding_digest: 'a'.repeat(64),
  auth_epoch: '5',
  api_authority_epoch: '6',
  runtime_host_installation_id: `wri_${'4'.repeat(32)}`,
  runtime_host_installation_revision: '7',
  runtime_epoch: '9',
  expires_at: '2026-09-06T00:00:00Z',
}

const attachment: WAWBrowserAttachmentIdentity = {
  attachmentId: ticket.attachment_id,
  workspaceId,
  projectId,
  agentType: 'codex',
  generation: ticket.generation,
  leaseNumber: ticket.lease_number,
  bindingRevision: ticket.binding_revision,
  bindingDigest: ticket.binding_digest,
  authEpoch: ticket.auth_epoch,
  apiAuthorityEpoch: ticket.api_authority_epoch,
  runtimeHostInstallationId: ticket.runtime_host_installation_id,
  runtimeHostInstallationRevision: ticket.runtime_host_installation_revision,
  runtimeEpoch: ticket.runtime_epoch,
}

const detachReceipt: WAWBrowserDetachReceipt = {
  workspace_id: workspaceId,
  attachment_id: ticket.attachment_id,
  generation: ticket.generation,
  lease_number: ticket.lease_number,
  result: 'detached',
  cleanup_state: 'ATTACH_PTY_CLOSED',
}

const stopReceipt = {
  workspace_id: workspaceId,
  project_id: projectId,
  agent_type: 'codex' as const,
  generation: ticket.generation,
  state: 'STOPPED',
}

function snapshot(
  overrides: Partial<WAWBrowserControllerSnapshot> = {},
): WAWBrowserControllerSnapshot {
  return Object.freeze({
    status: 'IDLE' as const,
    reason: null,
    attachment: null,
    outputCursor: null,
    freshRedrawTruncated: false,
    input: null,
    ...overrides,
  })
}

class FakeController implements WAWAttachmentControllerPort {
  #snapshot = snapshot()
  readonly connectRequests: WAWBrowserConnectRequest[] = []
  readonly controlRequests: WAWBrowserControlRequest[] = []
  readonly inputBytes: Uint8Array[] = []
  readonly inputReferences: Uint8Array[] = []
  readonly resizeRequests: Array<readonly [number, number]> = []
  readonly controlOrder: string[] = []

  constructor(readonly options: WAWBrowserControllerOptions) {}

  get snapshot(): WAWBrowserControllerSnapshot {
    return this.#snapshot
  }

  publish(next: WAWBrowserControllerSnapshot): void {
    this.#snapshot = next
    this.options.onSnapshot?.(next)
  }

  connect = vi.fn(async (request: WAWBrowserConnectRequest) => {
    this.connectRequests.push(request)
    await this.options.tickets.issue({
      workspaceId: request.workspaceId,
      agentType: request.agentType,
      reconnect: request.reconnect,
    })
    this.publish(snapshot({ status: 'CONNECTED', attachment }))
  })

  detach = vi.fn(
    async (
      request: WAWBrowserControlRequest,
    ): Promise<WAWBrowserDetachReceipt> => {
      this.controlRequests.push(request)
      const response = await this.options.controls.detach({
        workspaceId,
        attachmentId: ticket.attachment_id,
        generation: ticket.generation,
        leaseNumber: ticket.lease_number,
        agentType: 'codex',
        signal: request.context.signal,
      })
      this.controlOrder.push('detach')
      this.publish(snapshot({ status: 'DETACHED', attachment }))
      return response
    },
  )

  stop = vi.fn(
    async (
      request: WAWBrowserControlRequest,
    ): Promise<WAWBrowserStopOutcome> => {
      this.controlRequests.push(request)
      const detached = await this.options.controls.detach({
        workspaceId,
        attachmentId: ticket.attachment_id,
        generation: ticket.generation,
        leaseNumber: ticket.lease_number,
        agentType: 'codex',
        signal: request.context.signal,
      })
      this.controlOrder.push('detach')
      const stopped = await this.options.controls.stop({
        workspaceId,
        generation: ticket.generation,
        agentType: 'codex',
        signal: request.context.signal,
      })
      this.controlOrder.push('stop')
      this.publish(snapshot({ status: 'STOPPED', attachment: null }))
      return Object.freeze({
        detachConfirmed: true,
        detach: detached,
        stop: stopped,
      })
    },
  )

  sendInput = vi.fn(
    async (value: Uint8Array): Promise<WAWBrowserInputOutcome> => {
      this.inputReferences.push(value)
      this.inputBytes.push(new Uint8Array(value))
      return Object.freeze({
        browserHop: '1',
        cryptoSequence: '1',
        state: 'written_to_pty',
        reasonCode: null,
      })
    },
  )

  requestResize = vi.fn((columns: number, rows: number) => {
    this.resizeRequests.push(Object.freeze([columns, rows]))
  })

  contextChanged = vi.fn(() => {
    this.publish(
      snapshot({
        status: 'FENCED',
        reason: 'CONTEXT_CHANGED',
        attachment: this.#snapshot.attachment,
      }),
    )
  })

  handlePageLifecycle = vi.fn(
    (event: 'pagehide' | 'freeze' | 'hidden' | 'unmount') => {
      this.publish(
        snapshot({
          status: 'FENCED',
          reason:
            event === 'pagehide'
              ? 'PAGEHIDE'
              : event === 'freeze'
                ? 'PAGE_FROZEN'
                : event === 'hidden'
                  ? 'PAGE_HIDDEN'
                  : 'UNMOUNTED',
          attachment: this.#snapshot.attachment,
        }),
      )
    },
  )
}

function makeProvider(): WAWTrustProviderPort & {
  dispose: ReturnType<typeof vi.fn>
} {
  return {
    authority: 'independent',
    subscribeInvalidation: vi.fn(() => () => undefined),
    getAtomicSnapshot: vi.fn(async () => {
      throw new Error('not used by the controller seam')
    }),
    dispose: vi.fn(),
  }
}

function makeActions(order: string[] = []): WAWAttachmentActions {
  return {
    connect: vi.fn(async () => {
      order.push('ticket')
      return ticket
    }),
    reconnect: vi.fn(async () => {
      order.push('reconnect-ticket')
      return ticket
    }),
    detach: vi.fn(async () => {
      order.push('detach-request')
      return {
        request_id: `req_${'5'.repeat(32)}`,
        detach_operation_id: `dop_${'6'.repeat(32)}`,
        ...detachReceipt,
        state: 'RUNNING',
      }
    }),
    stop: vi.fn(async () => {
      order.push('stop-request')
      return {
        request_id: `req_${'7'.repeat(32)}`,
        stop_operation_id: `sop_${'8'.repeat(32)}`,
        ...stopReceipt,
      }
    }),
  }
}

function makeFixture(options: { readonly providerAvailable?: boolean } = {}) {
  const order: string[] = []
  const actions = makeActions(order)
  const provider = makeProvider()
  const trust = {
    authorize: vi.fn(),
    close: vi.fn(),
  } as unknown as ReturnType<
    NonNullable<WAWAttachmentDependencies['createTrust']>
  >
  const controllers: FakeController[] = []
  const createProvider = vi.fn(() => provider)
  const dependencies: WAWAttachmentDependencies = {
    providerAvailable: options.providerAvailable ?? true,
    createProvider,
    createTrust: vi.fn(() => trust),
    createController: vi.fn((controllerOptions) => {
      const controller = new FakeController(controllerOptions)
      controllers.push(controller)
      return controller
    }),
    origin: () => 'https://example.test',
  }
  return {
    actions,
    controllers,
    createProvider,
    dependencies,
    order,
    provider,
    trust,
  }
}

type HookProps = {
  authScope: string
  generation: string | null
  projectId: string | null
  runtime: WorkspaceRuntimeStatus | null
  workspaceId: string | null
}

function renderFixture(
  fixture: ReturnType<typeof makeFixture>,
  initial: Partial<HookProps> = {},
  wrapper?: React.ComponentType<{ children: React.ReactNode }>,
) {
  const epoch = { current: 1 } as MutableRefObject<number>
  const props: HookProps = {
    authScope: 'ses_test:csrf_test',
    generation: '7',
    projectId,
    runtime,
    workspaceId,
    ...initial,
  }
  const hook = renderHook(
    (input: HookProps) =>
      useWAWBrowserAttachment({
        actions: fixture.actions,
        agentType: 'codex',
        authScope: input.authScope,
        contextEpoch: epoch,
        generation: input.generation,
        projectId: input.projectId,
        runtime: input.runtime,
        workspaceId: input.workspaceId,
        dependencies: fixture.dependencies,
      }),
    { initialProps: props, wrapper },
  )
  return { ...hook, epoch, props }
}

function bindTerminal(
  current: {
    setSurface(surface: HTMLElement | null): void
    setViewport(viewport: HTMLElement | null): void
  },
  surface = document.createElement('div'),
  viewport = document.createElement('div'),
) {
  act(() => {
    current.setViewport(viewport)
    current.setSurface(surface)
  })
  return { surface, viewport }
}

function setVisibility(state: 'hidden' | 'visible'): void {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value: state,
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  setVisibility('visible')
})

describe('useWAWBrowserAttachment', () => {
  it('keeps Connect unavailable without a declared managed provider and never creates a ticket source', async () => {
    const fixture = makeFixture({ providerAvailable: false })
    const { result } = renderFixture(fixture)
    bindTerminal(result.current)

    expect(fixture.createProvider).not.toHaveBeenCalled()
    expect(result.current.canConnect).toBe(false)
    await act(async () => {
      await expect(result.current.connect()).rejects.toMatchObject({
        code: 'ATTACHMENT_UNAVAILABLE',
      })
    })
    expect(fixture.createProvider).not.toHaveBeenCalled()
    expect(fixture.actions.connect).not.toHaveBeenCalled()
    expect(result.current.view.status).toBe('UNAVAILABLE')
  })

  it('does not create a provider or request a ticket while the document is hidden', async () => {
    const fixture = makeFixture()
    const { result } = renderFixture(fixture)
    bindTerminal(result.current)
    setVisibility('hidden')
    act(() => document.dispatchEvent(new Event('visibilitychange')))

    await act(async () => {
      await expect(result.current.connect()).rejects.toMatchObject({
        code: 'CONTEXT_CHANGED',
      })
    })
    expect(fixture.createProvider).not.toHaveBeenCalled()
    expect(fixture.actions.connect).not.toHaveBeenCalled()
  })

  it('keeps an exact server ticket error instead of masking it as a protocol failure', async () => {
    const fixture = makeFixture()
    fixture.actions.connect = vi.fn(async () => {
      throw new ApiError({
        code: 'ATTACHMENT_STALE',
        message: 'exact server error',
        status: 409,
        requestId: 'req_exact',
      })
    })
    const { result } = renderFixture(fixture)
    bindTerminal(result.current)
    await act(async () => {
      await expect(result.current.connect()).rejects.toMatchObject({
        code: 'ATTACHMENT_STALE',
        requestId: 'req_exact',
      })
    })
    expect(result.current.error).toMatchObject({ code: 'ATTACHMENT_STALE' })
  })

  it('owns one ticket/trust/controller attempt and fences its stream and plaintext surface', async () => {
    const fixture = makeFixture()
    const { result } = renderFixture(fixture)
    const surface = document.createElement('div')
    surface.textContent = 'old terminal plaintext'
    bindTerminal(result.current, surface)

    await act(async () => {
      await result.current.connect()
    })
    const controller = fixture.controllers[0]!
    expect(fixture.createProvider).toHaveBeenCalledTimes(1)
    expect(fixture.dependencies.createTrust).toHaveBeenCalledWith(
      fixture.provider,
    )
    expect(controller.connectRequests).toHaveLength(1)
    expect(fixture.actions.connect).toHaveBeenCalledWith(
      workspaceId,
      'codex',
      expect.objectContaining({ aborted: false }),
    )
    expect(result.current.view.status).toBe('CONNECTED')
    expect(result.current.canInput).toBe(true)

    act(() => result.current.fence())
    expect(controller.contextChanged).toHaveBeenCalledTimes(1)
    expect(fixture.trust.close).toHaveBeenCalledTimes(1)
    expect(surface.textContent).toBe('')
    expect(result.current.view.status).toBe('FENCED')
    expect(result.current.canInput).toBe(false)
  })

  it('keeps a fresh strict control lease after pagehide and proves detach before Stop', async () => {
    const fixture = makeFixture()
    const { result } = renderFixture(fixture)
    bindTerminal(result.current)
    await act(async () => {
      await result.current.connect()
    })
    const controller = fixture.controllers[0]!
    const ticketSignal = vi.mocked(fixture.actions.connect).mock.calls[0]![2]!
    const clearInput = vi.fn()
    act(() => result.current.setInputClearer(clearInput))

    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(controller.handlePageLifecycle).toHaveBeenCalledWith('pagehide')
    expect(ticketSignal.aborted).toBe(true)
    expect(clearInput).toHaveBeenCalledTimes(1)
    expect(result.current.view.status).toBe('FENCED')
    expect(result.current.canControlStop).toBe(true)

    await act(async () => {
      await result.current.stop()
    })
    expect(controller.controlOrder).toEqual(['detach', 'stop'])
    expect(fixture.order).toContain('detach-request')
    expect(fixture.order).toContain('stop-request')
    const request = controller.controlRequests.at(-1)!
    expect(request.context.signal.aborted).toBe(false)
    expect(request.context.isCurrent()).toBe(true)
    expect(fixture.order.slice(-2)).toEqual(['detach-request', 'stop-request'])
  })

  it('fences synchronously from the document freeze target and does not restore input clearing', async () => {
    const fixture = makeFixture()
    const { result } = renderFixture(fixture)
    bindTerminal(result.current)
    await act(async () => {
      await result.current.connect()
    })
    const controller = fixture.controllers[0]!
    const clearInput = vi.fn()
    act(() => result.current.setInputClearer(clearInput))

    act(() => document.dispatchEvent(new Event('freeze')))
    expect(controller.handlePageLifecycle).toHaveBeenCalledWith('freeze')
    expect(clearInput).toHaveBeenCalledTimes(1)
    expect(result.current.view.status).toBe('FENCED')
    expect(result.current.canControlStop).toBe(true)
    act(() => window.dispatchEvent(new Event('pageshow')))
    expect(clearInput).toHaveBeenCalledTimes(1)
  })

  it('maps an aborted control fetch to CONTEXT_CHANGED instead of a stale transport error', async () => {
    const fixture = makeFixture()
    fixture.actions.detach = vi.fn(
      (
        _workspaceId,
        _attachmentId,
        _generation,
        _leaseNumber,
        _agentType,
        signal,
      ) =>
        new Promise<WorkspaceDetachResponse>((_, reject) => {
          signal?.addEventListener(
            'abort',
            () =>
              reject(
                new ApiError({
                  code: 'WAW_ACTION_STALE',
                  message: 'aborted fetch',
                  status: 0,
                }),
              ),
            { once: true },
          )
        }),
    )
    const { result } = renderFixture(fixture)
    bindTerminal(result.current)
    await act(async () => {
      await result.current.connect()
    })
    let stopping!: Promise<unknown>
    act(() => {
      stopping = result.current.stop()
    })
    act(() => result.current.fence())
    await expect(stopping).rejects.toMatchObject({ code: 'CONTEXT_CHANGED' })
  })

  it('uses only the visible terminal viewport for bounded resize requests', async () => {
    class ResizeObserverStub {
      static instances: ResizeObserverStub[] = []
      readonly observe = vi.fn()
      readonly disconnect = vi.fn()

      constructor(
        readonly callback: (entries: readonly ResizeObserverEntry[]) => void,
      ) {
        ResizeObserverStub.instances.push(this)
      }

      emit(target: Element, width: number, height: number): void {
        this.callback([
          {
            target,
            contentRect: { width, height },
          } as ResizeObserverEntry,
        ])
      }
    }
    vi.stubGlobal('ResizeObserver', ResizeObserverStub)
    const fixture = makeFixture()
    const { result } = renderFixture(fixture)
    const surface = document.createElement('div')
    const viewport = document.createElement('div')
    bindTerminal(result.current, surface, viewport)
    await act(async () => {
      await result.current.connect()
    })
    const controller = fixture.controllers[0]!
    const observer = ResizeObserverStub.instances[0]!
    expect(observer.observe).toHaveBeenCalledWith(viewport)

    act(() => observer.emit(viewport, 800, 400))
    expect(controller.resizeRequests.at(-1)).toEqual([96, 18])
    act(() => observer.emit(viewport, 10_000, 10_000))
    expect(controller.resizeRequests.at(-1)).toEqual([240, 200])
    expect(result.current).not.toHaveProperty('resize')
  })

  it('retains only bounded input outcome metadata and closes the second-input window', async () => {
    const fixture = makeFixture()
    const { result } = renderFixture(fixture)
    bindTerminal(result.current)
    await act(async () => {
      await result.current.connect()
    })
    const controller = fixture.controllers[0]!
    let resolve!: (value: WAWBrowserInputOutcome) => void
    const pending = new Promise<WAWBrowserInputOutcome>((accepted) => {
      resolve = accepted
    })
    controller.sendInput.mockImplementationOnce(async (value) => {
      controller.inputReferences.push(value)
      controller.inputBytes.push(new Uint8Array(value))
      return await pending
    })

    let sent!: Promise<WAWBrowserInputOutcome>
    act(() => {
      sent = result.current.sendInput('do-not-retain')
    })
    expect(controller.inputReferences[0]!.every((value) => value === 0)).toBe(
      true,
    )
    act(() => {
      controller.publish(
        snapshot({
          status: 'CONNECTED',
          attachment,
          input: {
            browserHop: '1',
            cryptoSequence: '1',
            state: 'published',
            reasonCode: null,
          },
        }),
      )
    })
    expect(result.current.canInput).toBe(false)
    await act(async () => {
      resolve(
        Object.freeze({
          browserHop: '1',
          cryptoSequence: '1',
          state: 'written_to_pty',
          reasonCode: null,
        }),
      )
      await sent
    })
    expect(result.current.view.lastInputOutcome).toEqual({
      state: 'written_to_pty',
      reasonCode: null,
    })
    expect(JSON.stringify(result.current.view)).not.toContain('do-not-retain')
  })

  it('clears and suppresses an old attachment before paint when auth or identity changes', async () => {
    const fixture = makeFixture()
    const rendered = renderFixture(fixture)
    const firstSurface = document.createElement('div')
    bindTerminal(rendered.result.current, firstSurface)
    await act(async () => {
      await rendered.result.current.connect()
    })
    const controller = fixture.controllers[0]!
    firstSurface.textContent = 'old terminal plaintext'
    const secondSurface = document.createElement('div')
    bindTerminal(rendered.result.current, secondSurface)
    expect(firstSurface.textContent).toBe('')
    expect(controller.contextChanged).toHaveBeenCalledTimes(1)

    secondSurface.textContent = 'old terminal plaintext'
    const identityChanged = {
      ...rendered.props,
      runtime: { ...runtime, runtime_epoch: '10' },
    }
    act(() => {
      rendered.rerender(identityChanged)
    })
    expect(secondSurface.textContent).toBe('')
    controller.publish(
      snapshot({
        status: 'CONNECTED',
        attachment,
        outputCursor: '99',
      }),
    )
    expect(rendered.result.current.view.status).toBe('IDLE')
    expect(rendered.result.current.view.outputCursor).toBeNull()

    secondSurface.textContent = 'old terminal plaintext'
    act(() => {
      rendered.rerender({
        ...identityChanged,
        authScope: 'ses_next:csrf_next',
      })
    })
    expect(secondSurface.textContent).toBe('')
  })

  it('marks an unerasable terminal surface as an output-render failure', () => {
    const fixture = makeFixture()
    const { result } = renderFixture(fixture)
    const surface = document.createElement('div')
    Object.defineProperty(surface, 'replaceChildren', {
      configurable: true,
      value: () => {
        throw new Error('replace failure')
      },
    })
    Object.defineProperty(surface, 'textContent', {
      configurable: true,
      get: () => 'retained plaintext',
      set: () => {
        throw new Error('text failure')
      },
    })
    act(() => result.current.setSurface(surface))
    act(() => result.current.fence())
    expect(result.current.error).toMatchObject({ code: 'OUTPUT_RENDER_FAILED' })
  })

  it('closes the right owner when construction fails before or after trust ownership', async () => {
    const providerBeforeTrust = makeProvider()
    const beforeTrust: WAWAttachmentDependencies = {
      providerAvailable: true,
      createProvider: () => providerBeforeTrust,
      createTrust: () => {
        throw new Error('trust construction failed')
      },
      origin: () => 'https://example.test',
    }
    const beforeFixture = makeFixture()
    beforeFixture.dependencies = beforeTrust
    const before = renderFixture(beforeFixture)
    bindTerminal(before.result.current)
    await act(async () => {
      await expect(before.result.current.connect()).rejects.toMatchObject({
        code: 'WAW_ACTION_FAILED',
      })
    })
    expect(providerBeforeTrust.dispose).toHaveBeenCalledTimes(1)

    const afterFixture = makeFixture()
    const close = vi.fn()
    afterFixture.dependencies = {
      ...afterFixture.dependencies,
      createTrust: () =>
        ({ authorize: vi.fn(), close }) as unknown as ReturnType<
          NonNullable<WAWAttachmentDependencies['createTrust']>
        >,
      origin: () => {
        throw new Error('origin construction failed')
      },
    }
    const after = renderFixture(afterFixture)
    bindTerminal(after.result.current)
    await act(async () => {
      await expect(after.result.current.connect()).rejects.toMatchObject({
        code: 'WAW_ACTION_FAILED',
      })
    })
    expect(close).toHaveBeenCalledTimes(1)
  })

  it('fences the admitted owner exactly once on StrictMode unmount', async () => {
    const fixture = makeFixture()
    const { result, unmount } = renderFixture(fixture, {}, ({ children }) => (
      <StrictMode>{children}</StrictMode>
    ))
    bindTerminal(result.current)
    await act(async () => {
      await result.current.connect()
    })
    const controller = fixture.controllers[0]!
    unmount()
    expect(controller.handlePageLifecycle).toHaveBeenCalledTimes(1)
    expect(controller.handlePageLifecycle).toHaveBeenCalledWith('unmount')
    expect(fixture.trust.close).toHaveBeenCalledTimes(1)
  })

  it('requires a current RUNNING Runtime identity before exposing browser operations', () => {
    const fixture = makeFixture()
    const { result } = renderFixture(fixture, {
      runtime: { ...runtime, state: 'NEEDS_INTERACTION' },
    })

    bindTerminal(result.current)
    expect(result.current.identity).not.toBeNull()
    expect(result.current.canConnect).toBe(false)
    expect(result.current.canInput).toBe(false)
    expect(result.current.canControlStop).toBe(false)
  })

  it('retains an admitted attachment for exact Stop when Runtime enters NEEDS_INTERACTION', async () => {
    const fixture = makeFixture()
    const rendered = renderFixture(fixture)
    bindTerminal(rendered.result.current)
    await act(async () => {
      await rendered.result.current.connect()
    })
    act(() => {
      rendered.rerender({
        ...rendered.props,
        runtime: { ...runtime, state: 'NEEDS_INTERACTION' },
      })
    })
    expect(rendered.result.current.canConnect).toBe(false)
    expect(rendered.result.current.view.attached).not.toBeNull()
    expect(rendered.result.current.canControlStop).toBe(true)
    await act(async () => {
      await rendered.result.current.stop()
    })
    expect(fixture.controllers[0]!.controlOrder).toEqual(['detach', 'stop'])
  })

  it.each(['TRUST_REQUIRED', 'LOGIN_REQUIRED'] as const)(
    'fences stream publication but retains exact Stop for %s',
    async (state) => {
      const fixture = makeFixture()
      const rendered = renderFixture(fixture)
      bindTerminal(rendered.result.current)
      await act(async () => {
        await rendered.result.current.connect()
      })
      act(() => {
        rendered.rerender({
          ...rendered.props,
          runtime: { ...runtime, state },
        })
      })
      expect(rendered.result.current.view.status).toBe('FENCED')
      expect(rendered.result.current.canInput).toBe(false)
      expect(rendered.result.current.canControlStop).toBe(true)
      await act(async () => {
        await rendered.result.current.stop()
      })
      expect(fixture.controllers[0]!.controlOrder).toEqual(['detach', 'stop'])
    },
  )
})
