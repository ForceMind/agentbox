import { describe, expect, it } from 'vitest'
import fixture from '../../../../../tests/fixtures/waw_trust/public-v1.json'
import {
  copyWAWTrustProviderSnapshot,
  WAWTrustPolicy,
  type WAWAuthenticatedRootCheckpoint,
  type WAWTrustAuthorizationRequest,
  type WAWTrustProviderSnapshot,
} from './wawTrustPolicy'
import {
  parseRootRecord,
  verifyTrustRecordSignature,
  WAWTrustRecordError,
} from './wawTrustRecords'

const encoder = new TextEncoder()
const ORIGIN = 'https://example.agentbox.test'
const HOST_ID = 'wri_0123456789abcdef0123456789abcdef'
const ROOT_FROM = '2030-01-01T00:00:00.000Z'
const ROOT_UNTIL = '2035-01-01T00:00:00.000Z'
const PIN_FROM = '2030-01-01T00:00:00.000Z'
const PIN_UNTIL = '2030-02-01T00:00:00.000Z'

const canonical = (value: object) =>
  JSON.stringify(
    Object.fromEntries(
      Object.entries(value).sort(([left], [right]) =>
        left < right ? -1 : left > right ? 1 : 0,
      ),
    ),
  )
const raw = (value: object) => encoder.encode(canonical(value))
const b64 = (value: Uint8Array) =>
  btoa(String.fromCharCode(...value))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
const sha256 = async (value: Uint8Array) =>
  Array.from(
    new Uint8Array(
      await crypto.subtle.digest('SHA-256', value as BufferSource),
    ),
    (byte) => byte.toString(16).padStart(2, '0'),
  ).join('')

const publicRecord = (name: string) =>
  fixture.records.find((record) => record.name === name)!.record

const request = (
  changes: Partial<WAWTrustAuthorizationRequest> = {},
): WAWTrustAuthorizationRequest => ({
  effective_origin: ORIGIN,
  admitted_api_origin: ORIGIN,
  runtime_host_installation_id: HOST_ID,
  runtime_host_installation_revision: '3',
  ...changes,
})

function publicSnapshot(
  changes: Partial<WAWTrustProviderSnapshot> = {},
): WAWTrustProviderSnapshot {
  return {
    schema_version: 'waw-trust-provider-snapshot-v1',
    provider_epoch: 'public-fixture-1',
    bootstrap_record: raw(fixture.bootstrap),
    root_records: [raw(publicRecord('root'))],
    pin_record: raw(publicRecord('pin')),
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

async function consume(
  policy: WAWTrustPolicy,
  snapshot: WAWTrustProviderSnapshot,
  actualRequest = request(),
  finalUtc = snapshot.trusted_time.utc,
) {
  return policy.consume(snapshot, actualRequest, {
    readEvidence: async (providerEpoch) => ({
      provider_epoch: providerEpoch,
      trusted_time: { utc: finalUtc, non_backward: true },
    }),
    isCurrent: () => true,
  })
}

interface TestKeys {
  readonly pair: CryptoKeyPair
  readonly publicKey: string
}

async function keys(): Promise<TestKeys> {
  const pair = (await crypto.subtle.generateKey('Ed25519', true, [
    'sign',
    'verify',
  ])) as CryptoKeyPair
  const publicKey = b64(
    new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey)),
  )
  return { pair, publicKey }
}

async function signRecord(
  domain: string,
  record: Record<string, unknown>,
  privateKey: CryptoKey,
): Promise<Record<string, unknown>> {
  const body = Object.fromEntries(
    Object.entries(record).filter(([key]) => key !== 'signature'),
  )
  const bytes = encoder.encode(`${domain}\0${canonical(body)}`)
  const signature = new Uint8Array(
    await crypto.subtle.sign('Ed25519', privateKey, bytes),
  )
  return { ...record, signature: b64(signature) }
}

async function syntheticRecords() {
  const bootstrap = await keys()
  const first = await keys()
  const second = await keys()
  const bootstrapRecord = {
    schema_version: 'waw-runtime-bootstrap-v1',
    key_id: 'bootstrap-2029',
    public_key: bootstrap.publicKey,
  }
  const root1 = await signRecord(
    'agentbox-waw/runtime-root/v1',
    {
      schema_version: 'waw-runtime-root-v1',
      root_revision: 1,
      key_id: 'synthetic-root-1',
      public_key: first.publicKey,
      signer_key_id: 'bootstrap-2029',
      state: 'ACTIVE',
      valid_from: ROOT_FROM,
      valid_until: ROOT_UNTIL,
      revoked_at: null,
      supersedes_key_id: null,
      signature_algorithm: 'Ed25519',
      signature: '',
    },
    bootstrap.pair.privateKey,
  )
  const root2 = await signRecord(
    'agentbox-waw/runtime-root/v1',
    {
      schema_version: 'waw-runtime-root-v1',
      root_revision: 2,
      key_id: 'synthetic-root-2',
      public_key: second.publicKey,
      signer_key_id: 'synthetic-root-1',
      state: 'ACTIVE',
      valid_from: ROOT_FROM,
      valid_until: ROOT_UNTIL,
      revoked_at: null,
      supersedes_key_id: 'synthetic-root-1',
      signature_algorithm: 'Ed25519',
      signature: '',
    },
    first.pair.privateKey,
  )
  const pin = async (
    signer: TestKeys,
    keyId: string,
    revision: number,
    fingerprint: string,
    changes: Record<string, unknown> = {},
  ) =>
    signRecord(
      'agentbox-waw/runtime-pin/v1',
      {
        schema_version: 'waw-runtime-pin.v1',
        repository: 'ForceMind/agentbox',
        origin: ORIGIN,
        pin_revision: revision,
        runtime_host_installation_id: HOST_ID,
        runtime_host_installation_revision: 3,
        runtime_attestation_x25519_fingerprint: fingerprint,
        valid_from: PIN_FROM,
        valid_until: PIN_UNTIL,
        revoked_at: null,
        supersedes_fingerprint: null,
        signature_algorithm: 'Ed25519',
        key_id: keyId,
        signature: '',
        ...changes,
      },
      signer.pair.privateKey,
    )
  return { bootstrap, first, second, bootstrapRecord, root1, root2, pin }
}

async function fullCheckpoint(
  rootRecords: readonly Record<string, unknown>[],
  acceptedAt = fixture.valid_test_time,
): Promise<WAWAuthenticatedRootCheckpoint> {
  const current = rootRecords.at(-1)!
  const signer = rootRecords.at(-2)!
  return {
    schema_version: 'waw-runtime-root-checkpoint-v1',
    root_revision: current.root_revision as number,
    key_id: current.key_id as string,
    public_key: current.public_key as string,
    signer_key_id: signer.key_id as string,
    signer_public_key: signer.public_key as string,
    root_history_sha256: await sha256(
      encoder.encode(
        JSON.stringify(rootRecords.map((record) => b64(raw(record)))),
      ),
    ),
    accepted_at: acceptedAt,
  }
}

function syntheticSnapshot(
  records: Awaited<ReturnType<typeof syntheticRecords>>,
  rootRecords: readonly Record<string, unknown>[],
  pinRecord: Record<string, unknown>,
  trustedUtc: string,
  checkpoint: WAWAuthenticatedRootCheckpoint | null = null,
): WAWTrustProviderSnapshot {
  const currentRoot = rootRecords.at(-1)!
  return publicSnapshot({
    provider_epoch: `synthetic-${String(currentRoot.root_revision)}-${String(pinRecord.pin_revision)}`,
    bootstrap_record: raw(records.bootstrapRecord),
    root_records: rootRecords.map(raw),
    pin_record: raw(pinRecord),
    authenticated_checkpoint: checkpoint,
    persisted_floors: {
      root_revision: currentRoot.root_revision as number,
      pin: {
        origin: ORIGIN,
        runtime_host_installation_id: HOST_ID,
        pin_revision: pinRecord.pin_revision as number,
      },
    },
    trusted_time: { utc: trustedUtc, non_backward: true },
  })
}

describe('bounded atomic provider snapshot copies', () => {
  it.each([
    ['bootstrap_record', 0],
    ['bootstrap_record', 4097],
    ['root_record', 0],
    ['root_record', 4097],
    ['pin_record', 0],
    ['pin_record', 4097],
  ] as const)('rejects %s byte length %i', (field, size) => {
    const bytes = new Uint8Array(size)
    const candidate = publicSnapshot(
      field === 'bootstrap_record'
        ? { bootstrap_record: bytes }
        : field === 'root_record'
          ? { root_records: [bytes] }
          : { pin_record: bytes },
    )
    expect(() => copyWAWTrustProviderSnapshot(candidate)).toThrow(
      WAWTrustRecordError,
    )
  })

  it('preflights every record before entering the record-copy pass', () => {
    const candidate = publicSnapshot()
    const roots = [...candidate.root_records]
    const root = roots[0]!
    let reads = 0
    Object.defineProperty(roots, 0, {
      get: () => {
        reads += 1
        return root
      },
    })
    const oversized = publicSnapshot({
      root_records: roots,
      pin_record: new Uint8Array(4097),
    })

    expect(() => copyWAWTrustProviderSnapshot(oversized)).toThrow(
      WAWTrustRecordError,
    )
    expect(reads).toBe(1)
  })

  it('owns record bytes independently of later provider mutation', () => {
    const candidate = publicSnapshot()
    const copied = copyWAWTrustProviderSnapshot(candidate)
    const expectedBootstrap = new Uint8Array(copied.bootstrap_record)
    const expectedRoot = new Uint8Array(copied.root_records[0]!)
    const expectedPin = new Uint8Array(copied.pin_record)

    candidate.bootstrap_record.fill(0)
    candidate.root_records[0]!.fill(0)
    candidate.pin_record.fill(0)

    expect(copied.bootstrap_record).toEqual(expectedBootstrap)
    expect(copied.root_records[0]).toEqual(expectedRoot)
    expect(copied.pin_record).toEqual(expectedPin)
  })
})

describe('public trust authorization metadata', () => {
  it('verifies the three immutable public signatures and authorizes only frozen pin metadata', async () => {
    const root1 = parseRootRecord(raw(publicRecord('root')))
    const root2 = parseRootRecord(raw(publicRecord('successor')))
    await expect(
      verifyTrustRecordSignature(root1, fixture.bootstrap.public_key),
    ).resolves.toBeUndefined()
    await expect(
      verifyTrustRecordSignature(
        root2,
        String(publicRecord('root').public_key),
      ),
    ).resolves.toBeUndefined()

    const authorization = await consume(new WAWTrustPolicy(), publicSnapshot())
    expect(authorization).toEqual({
      schema_version: 'waw-runtime-pin.v1',
      repository: 'ForceMind/agentbox',
      origin: ORIGIN,
      pin_revision: 7,
      runtime_host_installation_id: HOST_ID,
      runtime_host_installation_revision: 3,
      runtime_attestation_x25519_fingerprint: '1'.repeat(64),
      valid_from: PIN_FROM,
      valid_until: PIN_UNTIL,
      key_id: 'root-2029',
    })
    expect(Object.isFrozen(authorization)).toBe(true)
    expect(authorization).not.toHaveProperty('signature')
    expect(authorization).not.toHaveProperty('public_key')
    expect(authorization).not.toHaveProperty('admitted')
  })

  it.each([
    ['2029-12-31T23:55:00.000Z', true],
    ['2029-12-31T23:54:59.999Z', false],
    ['2030-02-01T00:05:00.000Z', true],
    ['2030-02-01T00:05:00.001Z', false],
  ])(
    'applies the sole +/-300 second active validity rule at %s',
    async (utc, valid) => {
      const pending = consume(
        new WAWTrustPolicy(),
        publicSnapshot({ trusted_time: { utc, non_backward: true } }),
        request(),
        utc,
      )
      if (valid) await expect(pending).resolves.not.toBeNull()
      else await expect(pending).rejects.toThrow(WAWTrustRecordError)
    },
  )

  it.each([
    request({ effective_origin: 'https://other.agentbox.test' }),
    request({ admitted_api_origin: 'https://other.agentbox.test' }),
    request({ runtime_host_installation_id: 'wri_' + 'f'.repeat(32) }),
    request({ runtime_host_installation_revision: '9007199254740992' }),
  ])(
    'rejects exact origin/host/wire revision mismatches',
    async (badRequest) => {
      await expect(
        consume(new WAWTrustPolicy(), publicSnapshot(), badRequest),
      ).rejects.toThrow(WAWTrustRecordError)
    },
  )
})

describe('synthetic lifecycle software verification', () => {
  it('accepts bootstrap -> root1 -> old-root-signed root2 and a current-root pin', async () => {
    const records = await syntheticRecords()
    const pin2 = await records.pin(
      records.second,
      'synthetic-root-2',
      1,
      '2'.repeat(64),
    )
    const snapshot = syntheticSnapshot(
      records,
      [records.root1, records.root2],
      pin2,
      fixture.valid_test_time,
      await fullCheckpoint([records.root1, records.root2]),
    )
    const policy = new WAWTrustPolicy()
    await expect(consume(policy, snapshot)).resolves.toMatchObject({
      key_id: 'synthetic-root-2',
      runtime_attestation_x25519_fingerprint: '2'.repeat(64),
    })
    await expect(consume(policy, snapshot)).resolves.toMatchObject({
      key_id: 'synthetic-root-2',
    })
  })

  it('rejects checkpoint digest, signer, and accepted-time replay mutations', async () => {
    const records = await syntheticRecords()
    const pin = await records.pin(
      records.second,
      'synthetic-root-2',
      1,
      '2'.repeat(64),
    )
    const checkpoint = await fullCheckpoint([records.root1, records.root2])
    for (const change of [
      { root_history_sha256: '0'.repeat(64) },
      { signer_public_key: records.second.publicKey },
      { accepted_at: '2031-01-01T00:00:00.000Z' },
    ]) {
      await expect(
        consume(
          new WAWTrustPolicy(),
          syntheticSnapshot(
            records,
            [records.root1, records.root2],
            pin,
            fixture.valid_test_time,
            { ...checkpoint, ...change },
          ),
        ),
      ).rejects.toThrow(WAWTrustRecordError)
    }
  })

  it('rejects a root revision skip before changing accepted state', async () => {
    const records = await syntheticRecords()
    const pin1 = await records.pin(
      records.first,
      'synthetic-root-1',
      1,
      '1'.repeat(64),
    )
    const skippedRoot = await signRecord(
      'agentbox-waw/runtime-root/v1',
      { ...records.root2, root_revision: 3, signature: '' },
      records.first.pair.privateKey,
    )
    await expect(
      consume(
        new WAWTrustPolicy(),
        syntheticSnapshot(
          records,
          [records.root1, skippedRoot],
          pin1,
          fixture.valid_test_time,
        ),
      ),
    ).rejects.toThrow(WAWTrustRecordError)
  })

  it('rejects a checkpoint transition whose predecessor and successor never overlap', async () => {
    const records = await syntheticRecords()
    const expiredRoot = await signRecord(
      'agentbox-waw/runtime-root/v1',
      {
        ...records.root1,
        valid_until: '2030-01-02T00:00:00.000Z',
        signature: '',
      },
      records.bootstrap.pair.privateKey,
    )
    const successor = await signRecord(
      'agentbox-waw/runtime-root/v1',
      {
        ...records.root2,
        valid_from: '2030-01-03T00:00:00.000Z',
        signature: '',
      },
      records.first.pair.privateKey,
    )
    const firstPin = await records.pin(
      records.first,
      'synthetic-root-1',
      1,
      '1'.repeat(64),
      { valid_until: '2030-01-02T00:00:00.000Z' },
    )
    const successorPin = await records.pin(
      records.second,
      'synthetic-root-2',
      2,
      '2'.repeat(64),
      {
        supersedes_fingerprint: '1'.repeat(64),
        valid_from: '2030-01-03T00:00:00.000Z',
      },
    )
    const policy = new WAWTrustPolicy()
    await consume(
      policy,
      syntheticSnapshot(
        records,
        [expiredRoot],
        firstPin,
        '2030-01-01T12:00:00.000Z',
      ),
    )

    await expect(
      consume(
        policy,
        syntheticSnapshot(
          records,
          [expiredRoot, successor],
          successorPin,
          '2030-01-03T00:00:00.000Z',
          await fullCheckpoint(
            [expiredRoot, successor],
            '2030-01-01T12:00:00.000Z',
          ),
        ),
      ),
    ).rejects.toThrow(WAWTrustRecordError)
  })

  it('rejects a truncated history even when its checkpoint fields are forged', async () => {
    const records = await syntheticRecords()
    const pin2 = await records.pin(
      records.second,
      'synthetic-root-2',
      1,
      '2'.repeat(64),
    )
    const without = syntheticSnapshot(
      records,
      [records.root2],
      pin2,
      fixture.valid_test_time,
    )
    await expect(consume(new WAWTrustPolicy(), without)).rejects.toThrow(
      WAWTrustRecordError,
    )
    const checkpoint: WAWAuthenticatedRootCheckpoint = {
      schema_version: 'waw-runtime-root-checkpoint-v1',
      root_revision: 2,
      key_id: 'synthetic-root-2',
      public_key: records.second.publicKey,
      signer_key_id: 'synthetic-root-1',
      signer_public_key: records.first.publicKey,
      root_history_sha256: await sha256(raw(records.root2)),
      accepted_at: fixture.valid_test_time,
    }
    const withCheckpoint = syntheticSnapshot(
      records,
      [records.root2],
      pin2,
      fixture.valid_test_time,
      checkpoint,
    )
    const checkpointPolicy = new WAWTrustPolicy()
    await expect(consume(checkpointPolicy, withCheckpoint)).rejects.toThrow(
      WAWTrustRecordError,
    )
    await expect(
      consume(
        new WAWTrustPolicy(),
        syntheticSnapshot(
          records,
          [records.root2],
          pin2,
          fixture.valid_test_time,
          {
            ...checkpoint,
            signer_public_key: records.second.publicKey,
          },
        ),
      ),
    ).rejects.toThrow(WAWTrustRecordError)
  })

  it('commits a bootstrap-signed same-key root revocation but never authorizes or reactivates it', async () => {
    const records = await syntheticRecords()
    const pin2 = await records.pin(
      records.second,
      'synthetic-root-2',
      1,
      '2'.repeat(64),
    )
    const policy = new WAWTrustPolicy()
    await consume(
      policy,
      syntheticSnapshot(
        records,
        [records.root1, records.root2],
        pin2,
        fixture.valid_test_time,
        await fullCheckpoint([records.root1, records.root2]),
      ),
    )
    const revokedRoot = await signRecord(
      'agentbox-waw/runtime-root/v1',
      {
        ...records.root2,
        root_revision: 3,
        signer_key_id: 'bootstrap-2029',
        state: 'REVOKED',
        revoked_at: '2030-01-20T00:00:00.000Z',
        supersedes_key_id: 'synthetic-root-2',
        signature: '',
      },
      records.bootstrap.pair.privateKey,
    )
    await expect(
      consume(
        policy,
        syntheticSnapshot(
          records,
          [records.root1, records.root2, revokedRoot],
          pin2,
          '2030-01-20T00:00:00.000Z',
          await fullCheckpoint([records.root1, records.root2]),
        ),
      ),
    ).resolves.toBeNull()

    const reactivated = await signRecord(
      'agentbox-waw/runtime-root/v1',
      {
        ...records.root2,
        root_revision: 4,
        signer_key_id: 'synthetic-root-2',
        state: 'ACTIVE',
        revoked_at: null,
        supersedes_key_id: 'synthetic-root-2',
        signature: '',
      },
      records.second.pair.privateKey,
    )
    await expect(
      consume(
        policy,
        syntheticSnapshot(
          records,
          [reactivated],
          pin2,
          '2030-01-20T00:00:00.000Z',
        ),
      ),
    ).rejects.toThrow(WAWTrustRecordError)
  })

  it('enforces pin floor, same scope, explicit supersession and revocation', async () => {
    const records = await syntheticRecords()
    const firstPin = await records.pin(
      records.first,
      'synthetic-root-1',
      7,
      '1'.repeat(64),
    )
    const policy = new WAWTrustPolicy()
    const initial = syntheticSnapshot(
      records,
      [records.root1],
      firstPin,
      fixture.valid_test_time,
    )
    await consume(policy, initial)

    const successorPin = await records.pin(
      records.first,
      'synthetic-root-1',
      8,
      '3'.repeat(64),
      {
        supersedes_fingerprint: '1'.repeat(64),
        valid_from: '2030-02-02T00:00:00.000Z',
        valid_until: '2030-03-01T00:00:00.000Z',
      },
    )
    const missingSupersession = await records.pin(
      records.first,
      'synthetic-root-1',
      8,
      '3'.repeat(64),
      {
        valid_from: '2030-02-02T00:00:00.000Z',
        valid_until: '2030-03-01T00:00:00.000Z',
      },
    )
    await expect(
      consume(
        policy,
        syntheticSnapshot(
          records,
          [records.root1],
          missingSupersession,
          '2030-02-02T00:00:00.000Z',
        ),
      ),
    ).rejects.toThrow(WAWTrustRecordError)
    const overlapping = await records.pin(
      records.first,
      'synthetic-root-1',
      8,
      '3'.repeat(64),
      {
        supersedes_fingerprint: '1'.repeat(64),
        valid_from: PIN_UNTIL,
        valid_until: '2030-03-01T00:00:00.000Z',
      },
    )
    await expect(
      consume(
        policy,
        syntheticSnapshot(records, [records.root1], overlapping, PIN_UNTIL),
      ),
    ).rejects.toThrow(WAWTrustRecordError)
    await expect(
      consume(
        policy,
        syntheticSnapshot(
          records,
          [records.root1],
          successorPin,
          '2030-02-02T00:00:00.000Z',
        ),
      ),
    ).resolves.toMatchObject({ pin_revision: 8 })

    const retiredReuse = await records.pin(
      records.first,
      'synthetic-root-1',
      9,
      '1'.repeat(64),
      {
        supersedes_fingerprint: '3'.repeat(64),
        valid_from: '2030-03-02T00:00:00.000Z',
        valid_until: '2030-04-01T00:00:00.000Z',
      },
    )
    await expect(
      consume(
        policy,
        syntheticSnapshot(
          records,
          [records.root1],
          retiredReuse,
          '2030-03-02T00:00:00.000Z',
        ),
      ),
    ).rejects.toThrow(WAWTrustRecordError)

    await expect(consume(policy, initial)).rejects.toThrow(WAWTrustRecordError)

    const revokedPin = await records.pin(
      records.first,
      'synthetic-root-1',
      9,
      '3'.repeat(64),
      {
        supersedes_fingerprint: '3'.repeat(64),
        valid_from: '2030-02-02T00:00:00.000Z',
        valid_until: '2030-03-01T00:00:00.000Z',
        revoked_at: '2030-02-10T00:00:00.000Z',
      },
    )
    await expect(
      consume(
        policy,
        syntheticSnapshot(
          records,
          [records.root1],
          revokedPin,
          '2030-02-10T00:00:00.000Z',
        ),
      ),
    ).resolves.toBeNull()

    const sameKeyReactivation = await records.pin(
      records.first,
      'synthetic-root-1',
      10,
      '3'.repeat(64),
      {
        supersedes_fingerprint: '3'.repeat(64),
        valid_from: '2030-03-02T00:00:00.000Z',
        valid_until: '2030-04-01T00:00:00.000Z',
      },
    )
    await expect(
      consume(
        policy,
        syntheticSnapshot(
          records,
          [records.root1],
          sameKeyReactivation,
          '2030-03-02T00:00:00.000Z',
        ),
      ),
    ).rejects.toThrow(WAWTrustRecordError)
  })

  it('keeps accepted records/floors atomic across invalid input and time rollback', async () => {
    const policy = new WAWTrustPolicy()
    const accepted = publicSnapshot()
    const first = await consume(policy, accepted)
    const badPin = raw({ ...publicRecord('pin'), signature: 'A'.repeat(86) })
    await expect(
      consume(policy, publicSnapshot({ pin_record: badPin })),
    ).rejects.toThrow(WAWTrustRecordError)
    await expect(
      consume(policy, accepted, request(), '2030-01-14T23:59:59.999Z'),
    ).rejects.toThrow(WAWTrustRecordError)
    await expect(consume(policy, accepted)).resolves.toEqual(first)
  })

  it('rejects an initial trusted-time rollback before final evidence can recover it', async () => {
    const policy = new WAWTrustPolicy()
    await consume(policy, publicSnapshot())
    let evidenceReads = 0
    const rolledBack = publicSnapshot({
      trusted_time: {
        utc: '2030-01-14T23:59:59.999Z',
        non_backward: true,
      },
    })

    await expect(
      policy.consume(rolledBack, request(), {
        readEvidence: async (providerEpoch) => {
          evidenceReads += 1
          return {
            provider_epoch: providerEpoch,
            trusted_time: {
              utc: fixture.valid_test_time,
              non_backward: true,
            },
          }
        },
        isCurrent: () => true,
      }),
    ).rejects.toThrow(WAWTrustRecordError)
    expect(evidenceReads).toBe(0)
    await expect(consume(policy, publicSnapshot())).resolves.not.toBeNull()
  })

  it('requires an exact synchronous commit guard and leaves accepted state unchanged on rejection', async () => {
    const policy = new WAWTrustPolicy()
    const epochs: string[] = []
    const asynchronousGuard = async () => true

    await expect(
      policy.consume(publicSnapshot(), request(), {
        readEvidence: async (providerEpoch) => {
          epochs.push(`read:${providerEpoch}`)
          return {
            provider_epoch: providerEpoch,
            trusted_time: {
              utc: fixture.valid_test_time,
              non_backward: true,
            },
          }
        },
        isCurrent: ((providerEpoch: string) => {
          epochs.push(`commit:${providerEpoch}`)
          return asynchronousGuard()
        }) as unknown as (providerEpoch: string) => boolean,
      }),
    ).rejects.toThrow(WAWTrustRecordError)
    expect(epochs).toEqual(['read:public-fixture-1', 'commit:public-fixture-1'])
    await expect(consume(policy, publicSnapshot())).resolves.not.toBeNull()
  })

  it('compares the largest signed safe Number to the wire string without rounding', async () => {
    const records = await syntheticRecords()
    const maximumPin = await records.pin(
      records.first,
      'synthetic-root-1',
      Number.MAX_SAFE_INTEGER,
      '4'.repeat(64),
      { runtime_host_installation_revision: Number.MAX_SAFE_INTEGER },
    )
    const snapshot = syntheticSnapshot(
      records,
      [records.root1],
      maximumPin,
      fixture.valid_test_time,
    )
    await expect(
      consume(
        new WAWTrustPolicy(),
        snapshot,
        request({
          runtime_host_installation_revision: String(Number.MAX_SAFE_INTEGER),
        }),
      ),
    ).resolves.toMatchObject({
      runtime_host_installation_revision: Number.MAX_SAFE_INTEGER,
    })
    await expect(
      consume(
        new WAWTrustPolicy(),
        snapshot,
        request({ runtime_host_installation_revision: '9007199254740992' }),
      ),
    ).rejects.toThrow(WAWTrustRecordError)
  })
})
