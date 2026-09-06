import { useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'

import { AuthContext } from '../src/features/auth/AuthContext'
import {
  type WAWAttachmentControllerPort,
  type WAWAttachmentDependencies,
} from '../src/features/workspace/useWAWBrowserAttachment'
import { useWorkspaceController } from '../src/features/workspace/useWorkspaceController'
import type {
  WAWBrowserAttachmentIdentity,
  WAWBrowserConnectRequest,
  WAWBrowserControllerOptions,
  WAWBrowserControllerSnapshot,
  WAWBrowserControlRequest,
  WAWBrowserDetachReceipt,
  WAWBrowserInputOutcome,
  WAWBrowserStopOutcome,
  WAWBrowserTerminalSchedulerPort,
} from '../src/features/workspace/wawBrowserController'
import { ApiClient } from '../src/lib/api'
import { WorkspacePage } from '../src/pages/WorkspacePage'
import '../src/styles.css'

const projectId = `prj_${'1'.repeat(32)}`
const terminalOutput = 'RC9 synthetic terminal output'

type HarnessEvidence = Readonly<{
  events: readonly string[]
  inputs: readonly Readonly<{
    byteLength: number
    endsWithCarriageReturn: boolean
  }>[]
  resizes: readonly Readonly<{ columns: number; rows: number }>[]
}>

let evidence: HarnessEvidence = Object.freeze({
  events: Object.freeze([]),
  inputs: Object.freeze([]),
  resizes: Object.freeze([]),
})
const listeners = new Set<() => void>()

function commitEvidence(next: HarnessEvidence) {
  evidence = Object.freeze(next)
  for (const listener of listeners) listener()
}

function recordEvent(event: string) {
  commitEvidence({
    ...evidence,
    events: Object.freeze([...evidence.events, event]),
  })
}

function recordInput(value: Uint8Array) {
  const copied = new Uint8Array(value)
  const input = Object.freeze({
    byteLength: copied.byteLength,
    endsWithCarriageReturn: copied[copied.length - 1] === 13,
  })
  copied.fill(0)
  commitEvidence({
    ...evidence,
    inputs: Object.freeze([...evidence.inputs, input]),
  })
}

function recordResize(columns: number, rows: number) {
  commitEvidence({
    ...evidence,
    resizes: Object.freeze([
      ...evidence.resizes,
      Object.freeze({ columns, rows }),
    ]),
  })
}

function emptySnapshot(): WAWBrowserControllerSnapshot {
  return Object.freeze({
    status: 'IDLE',
    reason: null,
    attachment: null,
    outputCursor: null,
    freshRedrawTruncated: false,
    input: null,
  })
}

class HarnessAttachmentController implements WAWAttachmentControllerPort {
  #snapshot = emptySnapshot()
  #terminal: WAWBrowserTerminalSchedulerPort | null = null

  constructor(readonly options: WAWBrowserControllerOptions) {}

  get snapshot(): WAWBrowserControllerSnapshot {
    return this.#snapshot
  }

  #publish(snapshot: WAWBrowserControllerSnapshot) {
    this.#snapshot = Object.freeze(snapshot)
    this.options.onSnapshot?.(this.#snapshot)
  }

  async connect(request: WAWBrowserConnectRequest): Promise<void> {
    recordEvent(
      request.reconnect ? 'controller:reconnect' : 'controller:connect',
    )
    recordEvent('trust:authorize')
    await this.options.trust.authorize({} as never)
    const ticket = await this.options.tickets.issue({
      workspaceId: request.workspaceId,
      agentType: request.agentType,
      reconnect: request.reconnect,
    })
    const attachment: WAWBrowserAttachmentIdentity = Object.freeze({
      attachmentId: ticket.attachment_id,
      workspaceId: ticket.workspace_id,
      projectId: ticket.project_id,
      agentType: ticket.agent_type,
      generation: ticket.generation,
      leaseNumber: ticket.lease_number,
      bindingRevision: ticket.binding_revision,
      bindingDigest: ticket.binding_digest,
      authEpoch: ticket.auth_epoch,
      apiAuthorityEpoch: ticket.api_authority_epoch,
      runtimeHostInstallationId: ticket.runtime_host_installation_id,
      runtimeHostInstallationRevision:
        ticket.runtime_host_installation_revision,
      runtimeEpoch: ticket.runtime_epoch,
    })
    this.#terminal = this.options.terminal.create({
      onFence: () => undefined,
    })
    this.#publish(
      Object.freeze({
        ...emptySnapshot(),
        status: 'CONNECTED',
        attachment,
      }),
    )
    await new Promise<void>((resolve) => window.setTimeout(resolve, 0))
    await this.#enqueueOutput()
  }

  async #enqueueOutput() {
    await this.#terminal?.enqueueFrame(
      new TextEncoder().encode(`${terminalOutput}\r\n`),
    )
  }

  async detach(
    request: WAWBrowserControlRequest,
  ): Promise<WAWBrowserDetachReceipt> {
    recordEvent('controller:detach')
    const attached = this.#snapshot.attachment
    if (attached === null) throw new Error('attachment unavailable')
    const receipt = await this.options.controls.detach({
      workspaceId: attached.workspaceId,
      attachmentId: attached.attachmentId,
      generation: attached.generation,
      leaseNumber: attached.leaseNumber,
      agentType: attached.agentType,
      signal: request.context.signal,
    })
    this.#terminal?.cancelAttachment()
    this.#publish(
      Object.freeze({
        ...emptySnapshot(),
        status: 'DETACHED',
        attachment: attached,
      }),
    )
    return receipt
  }

  async stop(
    request: WAWBrowserControlRequest,
  ): Promise<WAWBrowserStopOutcome> {
    recordEvent('controller:stop-request')
    const attached = this.#snapshot.attachment
    if (attached === null) throw new Error('attachment unavailable')
    const detach = await this.options.controls.detach({
      workspaceId: attached.workspaceId,
      attachmentId: attached.attachmentId,
      generation: attached.generation,
      leaseNumber: attached.leaseNumber,
      agentType: attached.agentType,
      signal: request.context.signal,
    })
    recordEvent('controller:stop:detach-confirmed')
    recordEvent('controller:stop')
    const stop = await this.options.controls.stop({
      workspaceId: attached.workspaceId,
      generation: attached.generation,
      agentType: attached.agentType,
      signal: request.context.signal,
    })
    this.#terminal?.cancelAttachment()
    this.#publish(Object.freeze({ ...emptySnapshot(), status: 'STOPPED' }))
    return Object.freeze({ detachConfirmed: true, detach, stop })
  }

  async sendInput(value: Uint8Array): Promise<WAWBrowserInputOutcome> {
    recordInput(value)
    return Object.freeze({
      browserHop: '1',
      cryptoSequence: '1',
      state: 'written_to_pty',
      reasonCode: null,
    })
  }

  requestResize(columns: number, rows: number): void {
    recordResize(columns, rows)
    this.#terminal?.resize(columns, rows)
    const terminal = this.#terminal
    if (terminal !== null) {
      window.setTimeout(() => {
        void terminal
          .enqueueFrame(new TextEncoder().encode(`${terminalOutput}\r\n`))
          .catch(() => undefined)
      }, 50)
    }
  }

  contextChanged(): void {
    this.#terminal?.cancelAttachment()
    this.#publish(
      Object.freeze({
        ...emptySnapshot(),
        status: 'FENCED',
        reason: 'CONTEXT_CHANGED',
        attachment: this.#snapshot.attachment,
      }),
    )
  }

  handlePageLifecycle(
    event: 'pagehide' | 'freeze' | 'hidden' | 'unmount',
  ): void {
    recordEvent(`lifecycle:${event}`)
    this.#terminal?.cancelAttachment()
  }
}

const attachmentDependencies: WAWAttachmentDependencies = Object.freeze({
  providerAvailable: true,
  createProvider: () => {
    recordEvent('provider:create')
    return {
      authority: 'independent',
      subscribeInvalidation: () => () => undefined,
      getAtomicSnapshot: async () => {
        throw new Error('synthetic controller owns the trust response')
      },
      dispose: () => recordEvent('provider:dispose'),
    }
  },
  createTrust: (provider) => ({
    authorize: async () => Object.freeze({}) as never,
    close: () => {
      recordEvent('trust:close')
      provider.dispose()
    },
  }),
  createController: (options) => new HarnessAttachmentController(options),
  origin: () => window.location.origin,
})

const api = new ApiClient()
const auth = Object.freeze({
  user: { id: `adm_${'9'.repeat(32)}`, username: '用户管理员' },
  session: {
    id: `ses_${'8'.repeat(32)}`,
    expires_at: '2026-12-31T00:00:00Z',
  },
  csrf_token: 'csrf-rc9-workspace',
})

export function WorkspaceHarness() {
  const model = useWorkspaceController({
    projectId,
    agentType: 'codex',
    attachmentDependencies,
  })

  return <WorkspacePage model={model} />
}

export function Harness() {
  const currentEvidence = useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => evidence,
    () => evidence,
  )

  return (
    <AuthContext.Provider
      value={{
        api,
        auth,
        status: 'authenticated',
        login: async () => undefined,
        logout: async () => undefined,
        refresh: async () => auth,
      }}
    >
      <WorkspaceHarness />
      <output data-testid="workspace-harness-evidence" hidden>
        {JSON.stringify(currentEvidence)}
      </output>
    </AuthContext.Provider>
  )
}

const root = document.getElementById('root')
if (root === null) throw new Error('Workspace E2E harness root is missing')
createRoot(root).render(<Harness />)
