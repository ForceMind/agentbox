import { describe, expect, it, vi } from 'vitest'

import { ChromiumWAWTrustProviderPort } from './wawTrustChromiumPort'

class EventPort {
  readonly messageListeners: ((message: unknown) => void)[] = []
  readonly disconnectListeners: (() => void)[] = []
  readonly onMessage = {
    addListener: (listener: (message: unknown) => void) =>
      this.messageListeners.push(listener),
  }
  readonly onDisconnect = {
    addListener: (listener: () => void) =>
      this.disconnectListeners.push(listener),
  }
  readonly sent: unknown[] = []
  disconnected = false

  postMessage(message: unknown): void {
    this.sent.push(message)
  }

  disconnect(): void {
    this.disconnected = true
  }

  respond(type: string, body: Record<string, unknown> = {}): void {
    const request = this.sent.at(-1) as Record<string, unknown>
    this.messageListeners[0]?.({
      type,
      protocol_version: 1,
      page_nonce: request.page_nonce,
      sequence: String(this.sent.length),
      correlation_id: request.correlation_id,
      ...body,
    })
  }
}

function runtime(port: EventPort) {
  return {
    connect: vi.fn(() => port),
  }
}

function snapshotBody() {
  const record = (value: object) =>
    btoa(JSON.stringify(value))
      .replaceAll('+', '-')
      .replaceAll('/', '_')
      .replace(/=+$/, '')
  return {
    schema_version: 'waw-trust-provider-snapshot-v1',
    provider_epoch: 'pte_test',
    bootstrap_record: record({ bootstrap: 1 }),
    root_records: [record({ root: 1 })],
    pin_record: record({ pin: 1 }),
    authenticated_checkpoint: null,
    persisted_floors: {},
    trusted_time: {},
    origin_network_proof: {},
  }
}

async function open(port: EventPort): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  expect(port.sent).toHaveLength(1)
  port.respond('OPENED', {
    provider_installation_id: `bti_${'1'.repeat(32)}`,
    provider_epoch: 'pte_test',
    document_id: '12345678-abcd-4321-abcd-123456789abc',
    origin: 'https://example.agentbox.test',
  })
}

describe('managed Chromium trust provider adapter', () => {
  it('opens the fixed extension and decodes one bounded atomic snapshot', async () => {
    const port = new EventPort()
    const provider = new ChromiumWAWTrustProviderPort(
      runtime(port),
      'a'.repeat(32),
    )
    await open(port)
    const pending = provider.getAtomicSnapshot()
    await vi.waitFor(() => expect(port.sent).toHaveLength(2))
    port.respond('SNAPSHOT', {
      snapshot: snapshotBody(),
    })
    await expect(pending).resolves.toMatchObject({
      schema_version: 'waw-trust-provider-snapshot-v1',
      provider_epoch: 'pte_test',
    })
    provider.close()
  })

  it('invalidates all listeners and pending work on sequence failure', async () => {
    const port = new EventPort()
    const provider = new ChromiumWAWTrustProviderPort(
      runtime(port),
      'b'.repeat(32),
    )
    const reasons: string[] = []
    provider.subscribeInvalidation((reason) => reasons.push(reason))
    port.messageListeners[0]?.({
      type: 'OPENED',
      protocol_version: 1,
      page_nonce: 'x'.repeat(43),
      sequence: '2',
      correlation_id: `req_${'1'.repeat(32)}`,
    })
    await expect(provider.getAtomicSnapshot()).rejects.toThrow(
      'RUNTIME_ATTESTATION_UNVERIFIED',
    )
    expect(reasons).toEqual(['lost'])
    expect(port.disconnected).toBe(true)
  })

  it('rejects non-Chrome extension identifiers', () => {
    expect(
      () =>
        new ChromiumWAWTrustProviderPort(runtime(new EventPort()), 'not-an-id'),
    ).toThrow('RUNTIME_ATTESTATION_UNVERIFIED')
  })

  it('keeps the provider session live with ordered five-second heartbeats', async () => {
    vi.useFakeTimers()
    try {
      const port = new EventPort()
      const provider = new ChromiumWAWTrustProviderPort(
        runtime(port),
        'c'.repeat(32),
      )
      const reasons: string[] = []
      provider.subscribeInvalidation((reason) => reasons.push(reason))
      await open(port)
      await vi.advanceTimersByTimeAsync(5000)
      expect(port.sent.at(-1)).toMatchObject({ type: 'PING', sequence: '2' })
      const queuedSnapshot = provider.getAtomicSnapshot()
      expect(port.sent).toHaveLength(2)
      port.respond('PONG')
      await vi.advanceTimersByTimeAsync(0)
      expect(port.sent.at(-1)).toMatchObject({
        type: 'SNAPSHOT_GET',
        sequence: '3',
      })
      port.respond('SNAPSHOT', { snapshot: snapshotBody() })
      await expect(queuedSnapshot).resolves.toMatchObject({
        provider_epoch: 'pte_test',
      })
      await vi.advanceTimersByTimeAsync(5000)
      expect(port.sent.at(-1)).toMatchObject({ type: 'PING', sequence: '4' })
      expect(reasons).toEqual([])
      provider.close()
      expect(reasons).toEqual(['closed'])
    } finally {
      vi.useRealTimers()
    }
  })

  it('disposes a pending OPEN once and ignores a late native replay', async () => {
    const port = new EventPort()
    const provider = new ChromiumWAWTrustProviderPort(
      runtime(port),
      'd'.repeat(32),
    )
    const pending = provider.getAtomicSnapshot()
    await Promise.resolve()
    await Promise.resolve()
    expect(port.sent).toHaveLength(1)
    provider.dispose()
    port.respond('OPENED', {
      provider_installation_id: `bti_${'1'.repeat(32)}`,
      provider_epoch: 'pte_test',
      document_id: '12345678-abcd-4321-abcd-123456789abc',
      origin: 'https://example.agentbox.test',
    })
    await expect(pending).rejects.toThrow('RUNTIME_ATTESTATION_UNVERIFIED')
    expect(port.disconnected).toBe(true)
    expect(port.sent).toHaveLength(1)
  })
})
