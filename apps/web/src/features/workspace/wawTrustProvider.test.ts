import { afterEach, describe, expect, it, vi } from 'vitest'
import fixture from '../../../../../tests/fixtures/waw_trust/public-v1.json'
import type { WAWTrustProviderSnapshot } from './wawTrustPolicy'
import {
  WAWTrustProviderConsumer,
  type WAWTrustProviderInvalidation,
  type WAWTrustProviderPort,
} from './wawTrustProvider'
import { WAWTrustRecordError } from './wawTrustRecords'

const encoder = new TextEncoder()
const ORIGIN = 'https://example.agentbox.test'
const HOST_ID = 'wri_0123456789abcdef0123456789abcdef'
const canonical = (value: object) =>
  JSON.stringify(
    Object.fromEntries(
      Object.entries(value).sort(([left], [right]) =>
        left < right ? -1 : left > right ? 1 : 0,
      ),
    ),
  )
const raw = (value: object) => encoder.encode(canonical(value))
const record = (name: string) =>
  fixture.records.find((item) => item.name === name)!.record

function snapshot(
  changes: Partial<WAWTrustProviderSnapshot> = {},
): WAWTrustProviderSnapshot {
  return {
    schema_version: 'waw-trust-provider-snapshot-v1',
    provider_epoch: 'synthetic-port-1',
    bootstrap_record: raw(fixture.bootstrap),
    root_records: [raw(record('root'))],
    pin_record: raw(record('pin')),
    authenticated_checkpoint: null,
    persisted_floors: {
      root_revision: 1,
      pin: {
        origin: ORIGIN,
        runtime_host_installation_id: HOST_ID,
        pin_revision: 7,
      },
    },
    trusted_time: { utc: fixture.valid_test_time, non_backward: true },
    origin_network_proof: {
      effective_origin: ORIGIN,
      admitted_api_origin: ORIGIN,
      runtime_host_installation_id: HOST_ID,
      network_policy: 'production',
      verified: true,
    },
    ...changes,
  }
}

const request = {
  effective_origin: ORIGIN,
  admitted_api_origin: ORIGIN,
  runtime_host_installation_id: HOST_ID,
  runtime_host_installation_revision: '3',
} as const

class SyntheticPort implements WAWTrustProviderPort {
  readonly authority = 'synthetic-test' as const
  readonly events: string[] = []
  snapshots: WAWTrustProviderSnapshot[]
  listener: ((reason: WAWTrustProviderInvalidation) => void) | null = null
  failSnapshot = false
  disposed = false

  constructor(...snapshots: WAWTrustProviderSnapshot[]) {
    this.snapshots = snapshots
  }

  subscribeInvalidation(
    listener: (reason: WAWTrustProviderInvalidation) => void,
  ): () => void {
    this.events.push('subscribe')
    this.listener = listener
    return () => {
      this.events.push('unsubscribe')
      if (this.listener === listener) this.listener = null
    }
  }

  async getAtomicSnapshot(): Promise<WAWTrustProviderSnapshot> {
    if (this.disposed) throw new Error('synthetic provider disposed')
    this.events.push('snapshot')
    if (this.failSnapshot) throw new Error('synthetic provider unavailable')
    return this.snapshots.length > 1
      ? this.snapshots.shift()!
      : this.snapshots[0]!
  }

  invalidate(reason: WAWTrustProviderInvalidation): void {
    this.events.push(reason)
    this.listener?.(reason)
  }

  dispose(): void {
    this.disposed = true
  }
}

function consumer(port: SyntheticPort) {
  return new WAWTrustProviderConsumer([port], {
    mode: 'synthetic-test',
  })
}

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

afterEach(() => vi.restoreAllMocks())

describe('explicit provider selection and subscription order', () => {
  it('fails closed for missing, ambiguous, or synthetic-in-production ports', async () => {
    const one = new SyntheticPort(snapshot())
    const two = new SyntheticPort(snapshot())
    await expect(
      new WAWTrustProviderConsumer([]).authorize(request),
    ).rejects.toThrow(WAWTrustRecordError)
    await expect(
      new WAWTrustProviderConsumer([one, two], {
        mode: 'synthetic-test',
      }).authorize(request),
    ).rejects.toThrow(WAWTrustRecordError)
    await expect(
      new WAWTrustProviderConsumer([one]).authorize(request),
    ).rejects.toThrow(WAWTrustRecordError)
    expect(one.events).toEqual([])
  })

  it('subscribes before its atomic snapshot and returns frozen pin metadata', async () => {
    const port = new SyntheticPort(snapshot())
    const trust = consumer(port)
    const authorization = await trust.authorize(request)
    expect(port.events).toEqual(['subscribe', 'snapshot', 'snapshot'])
    expect(authorization).toMatchObject({
      pin_revision: 7,
      key_id: 'root-2029',
    })
    expect(Object.isFrozen(authorization)).toBe(true)
    expect(authorization.generation).toBeGreaterThan(0)
    expect(authorization.signal.aborted).toBe(false)
    expect(authorization.isCurrent()).toBe(true)
    expect(trust.currentAuthorization).toBe(authorization)
    trust.close()
    expect(trust.currentAuthorization).toBeNull()
    expect(authorization.signal.aborted).toBe(true)
    expect(authorization.isCurrent()).toBe(false)
    expect(port.events.at(-1)).toBe('unsubscribe')
    expect(port.disposed).toBe(true)
  })

  it('synchronously aborts a completed generation on every provider invalidation class', async () => {
    for (const reason of [
      'changed',
      'lost',
      'closed',
      'time-backward',
    ] as const) {
      const port = new SyntheticPort(snapshot())
      const trust = consumer(port)
      const authorization = await trust.authorize(request)
      let aborts = 0
      authorization.signal.addEventListener('abort', () => {
        aborts += 1
        expect(authorization.isCurrent()).toBe(false)
        expect(trust.currentAuthorization).toBeNull()
      })
      port.invalidate(reason)
      expect(trust.currentAuthorization).toBeNull()
      expect(authorization.signal.aborted).toBe(true)
      expect(aborts).toBe(1)
      trust.close()
      expect(
        port.events.filter((event) => event === 'unsubscribe'),
      ).toHaveLength(1)
    }
  })

  it('unsubscribes a failed authorization exactly once', async () => {
    const port = new SyntheticPort(
      snapshot({ pin_record: new Uint8Array(4097) }),
    )
    const trust = consumer(port)
    await expect(trust.authorize(request)).rejects.toThrow(WAWTrustRecordError)
    expect(port.events).toEqual(['subscribe', 'snapshot', 'unsubscribe'])
    trust.close()
    expect(port.events.filter((event) => event === 'unsubscribe')).toHaveLength(
      1,
    )
  })
})

describe('provider currentness and asynchronous invalidation races', () => {
  it.each(['lost', 'closed', 'time-backward'] as const)(
    'rejects a late signature result after provider %s',
    async (reason) => {
      const port = new SyntheticPort(snapshot())
      const trust = consumer(port)
      const entered = deferred()
      const release = deferred()
      const original = crypto.subtle.verify.bind(crypto.subtle)
      vi.spyOn(crypto.subtle, 'verify').mockImplementation(
        async (algorithm, key, signature, data) => {
          entered.resolve()
          await release.promise
          return original(algorithm, key, signature, data)
        },
      )
      const pending = trust.authorize(request)
      const rejected = expect(pending).rejects.toThrow(WAWTrustRecordError)
      await entered.promise
      if (reason === 'time-backward') {
        port.snapshots = [
          snapshot({
            trusted_time: {
              utc: '2030-01-14T23:59:59.999Z',
              non_backward: true,
            },
          }),
        ]
      }
      port.invalidate(reason)
      release.resolve()
      await rejected
      expect(trust.currentAuthorization).toBeNull()

      vi.restoreAllMocks()
      const replacement = consumer(new SyntheticPort(snapshot()))
      await expect(replacement.authorize(request)).resolves.toMatchObject({
        pin_revision: 7,
      })
      replacement.close()
    },
  )

  it('rejects an epoch or authority-field change even without an invalidation callback', async () => {
    const changedEpoch = new SyntheticPort(
      snapshot(),
      snapshot({ provider_epoch: 'synthetic-port-2' }),
    )
    await expect(consumer(changedEpoch).authorize(request)).rejects.toThrow(
      WAWTrustRecordError,
    )

    const changedFloor = new SyntheticPort(
      snapshot(),
      snapshot({
        persisted_floors: {
          root_revision: 1,
          pin: {
            origin: ORIGIN,
            runtime_host_installation_id: HOST_ID,
            pin_revision: 8,
          },
        },
      }),
    )
    await expect(consumer(changedFloor).authorize(request)).rejects.toThrow(
      WAWTrustRecordError,
    )

    const backwardTime = new SyntheticPort(
      snapshot(),
      snapshot({
        trusted_time: {
          utc: '2030-01-14T23:59:59.999Z',
          non_backward: true,
        },
      }),
    )
    await expect(consumer(backwardTime).authorize(request)).rejects.toThrow(
      WAWTrustRecordError,
    )
  })

  it('rejects mutation of provider-owned bytes after the initial defensive copy', async () => {
    const shared = snapshot()
    const port = new SyntheticPort(shared)
    const trust = consumer(port)
    const entered = deferred()
    const release = deferred()
    const original = crypto.subtle.verify.bind(crypto.subtle)
    let calls = 0
    vi.spyOn(crypto.subtle, 'verify').mockImplementation(
      async (algorithm, key, signature, data) => {
        calls += 1
        if (calls === 1) {
          entered.resolve()
          await release.promise
        }
        return original(algorithm, key, signature, data)
      },
    )

    const pending = trust.authorize(request)
    const rejected = expect(pending).rejects.toThrow(WAWTrustRecordError)
    await entered.promise
    shared.pin_record.fill(0)
    release.resolve()
    await rejected

    expect(trust.currentAuthorization).toBeNull()
    expect(port.events.filter((event) => event === 'unsubscribe')).toHaveLength(
      1,
    )
  })

  it('rejects provider loss while obtaining the confirmation snapshot', async () => {
    const port = new SyntheticPort(snapshot())
    let calls = 0
    const original = port.getAtomicSnapshot.bind(port)
    vi.spyOn(port, 'getAtomicSnapshot').mockImplementation(async () => {
      calls += 1
      if (calls === 2) {
        port.failSnapshot = true
        port.invalidate('lost')
      }
      return original()
    })
    const trust = consumer(port)
    await expect(trust.authorize(request)).rejects.toThrow(WAWTrustRecordError)
    expect(trust.currentAuthorization).toBeNull()
    expect(port.events.filter((event) => event === 'unsubscribe')).toHaveLength(
      1,
    )
    trust.close()
    expect(port.events.filter((event) => event === 'unsubscribe')).toHaveLength(
      1,
    )
  })

  it('does not let an older failed attempt clear or unsubscribe a newer registration', async () => {
    const port = new SyntheticPort(snapshot())
    const trust = consumer(port)
    const entered = deferred()
    const release = deferred()
    const original = crypto.subtle.verify.bind(crypto.subtle)
    let calls = 0
    vi.spyOn(crypto.subtle, 'verify').mockImplementation(
      async (algorithm, key, signature, data) => {
        calls += 1
        if (calls === 1) {
          entered.resolve()
          await release.promise
        }
        return original(algorithm, key, signature, data)
      },
    )

    const olderPending = trust.authorize(request)
    const olderRejected =
      expect(olderPending).rejects.toThrow(WAWTrustRecordError)
    await entered.promise
    const newer = await trust.authorize(request)
    expect(newer.isCurrent()).toBe(true)
    expect(newer.signal.aborted).toBe(false)
    release.resolve()
    await olderRejected

    expect(trust.currentAuthorization).toBe(newer)
    expect(newer.isCurrent()).toBe(true)
    expect(newer.signal.aborted).toBe(false)
    expect(port.events.filter((event) => event === 'subscribe')).toHaveLength(2)
    expect(port.events.filter((event) => event === 'unsubscribe')).toHaveLength(
      1,
    )

    trust.close()
    expect(newer.signal.aborted).toBe(true)
    expect(port.events.filter((event) => event === 'unsubscribe')).toHaveLength(
      2,
    )
  })
})
