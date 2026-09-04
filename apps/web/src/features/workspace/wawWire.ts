/** Closed WAW v1 direction profiles. Data validation supplies no admission authority. */
import { decodeAwce } from './awce'
import {
  ADMISSION_KEYS,
  CONTEXT_KEYS,
  U64_MAX,
  exactRecord,
  validateAdmission,
  validateContext,
  deriveContext,
  validateU64,
  type AdmissionTuple,
  type HandshakeContext,
} from './wawCryptoContext'

export const FrameType = Object.freeze({
  WS_HELLO: 1,
  RUNTIME_HELLO: 2,
  KEY_INIT: 3,
  KEY_ATTEST: 4,
  KEY_CONFIRM: 5,
  KEY_CONFIRM_ACK: 6,
  HELLO_ACK: 7,
  ADMITTED: 8,
  INPUT: 9,
  OUTPUT: 10,
  RESIZE: 11,
  HEARTBEAT: 12,
  PING: 13,
  PONG: 14,
  DETACH: 15,
  EXIT: 16,
  GAP: 17,
  ACK: 18,
  ERROR: 19,
  CLOSE: 20,
  STATE: 21,
  STREAM_READY: 22,
  STREAM_READY_ACK: 23,
  ADMISSION_COMMIT: 24,
  ADMISSION_COMMIT_ACK: 25,
  RESIZE_ACK: 26,
  DETACH_ACK: 27,
} as const)
export type FrameType = (typeof FrameType)[keyof typeof FrameType]
export const Leg = Object.freeze({
  BROWSER_TO_API: 'browser-to-api',
  API_TO_BROWSER: 'api-to-browser',
  API_TO_RUNTIME: 'api-to-runtime',
  RUNTIME_TO_API: 'runtime-to-api',
} as const)
export type Leg = (typeof Leg)[keyof typeof Leg]
const BA = Leg.BROWSER_TO_API,
  AB = Leg.API_TO_BROWSER,
  AR = Leg.API_TO_RUNTIME,
  RA = Leg.RUNTIME_TO_API
export const MAX_CONTROL_BYTES = 4096,
  MAX_FRAME_BYTES = 65536,
  INPUT_LIMIT = 16384,
  OUTPUT_LIMIT = 32768
const VALIDATION_MS = 5,
  ADMISSION_NS = 5_000_000_000n
const ALLOWED: Record<Leg, readonly number[]> = {
  'browser-to-api': [1, 3, 5, 9, 11, 12, 13, 15],
  'api-to-browser': [4, 6, 8, 10, 14, 16, 17, 18, 19, 20, 21, 26, 27],
  'api-to-runtime': [2, 3, 5, 9, 11, 12, 13, 14, 15, 20, 22, 24],
  'runtime-to-api': [
    4, 6, 7, 10, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 26, 27,
  ],
}
const HANDSHAKE: Record<Leg, readonly number[]> = {
  'browser-to-api': [1, 3, 5],
  'api-to-browser': [4, 6, 8],
  'api-to-runtime': [2, 3, 5, 22, 24],
  'runtime-to-api': [7, 4, 6, 23, 25],
}
const SCHEMAS: Record<Leg, Record<number, Record<string, string>>> = {
  'browser-to-api': {
    '1': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      resume_cursor: 'nullable_cursor',
      previous_runtime_epoch: 'nullable_u64',
      ticket: 'wat',
    },
    '3': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      noise_protocol: 'noise',
      crypto_envelope_version: 'one',
      browser_ephemeral_public_key: 'b64_32',
      noise_message_1: 'b64_32',
    },
    '5': {
      protocol_version: 'one',
      workspace_id: 'context',
      project_id: 'context',
      generation: 'context',
      binding_revision: 'context',
      binding_digest: 'context',
      lease_number: 'context',
      agent_type: 'context',
      api_authority_epoch: 'context',
      attachment_id: 'context',
      runtime_epoch: 'context',
      protocol_id: 'context',
      crypto_envelope_version: 'context',
      runtime_host_installation_revision: 'context',
      auth_epoch: 'context',
      runtime_host_installation_id: 'context',
      noise_protocol: 'noise',
      ciphertext: 'b64_48',
    },
    '11': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
      columns: 'columns',
      rows: 'rows',
    },
    '12': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
      sent_at_monotonic_tick: 'u64',
    },
    '13': {
      protocol_version: 'one',
      nonce: 'hex8',
      sent_at_monotonic_tick: 'u64',
    },
    '15': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
    },
  },
  'api-to-browser': {
    '4': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      noise_protocol: 'noise',
      crypto_envelope_version: 'one',
      runtime_attestation_x25519_fingerprint: 'hex32',
      runtime_ephemeral_public_key: 'b64_32',
      noise_message_2: 'b64_128',
    },
    '6': {
      protocol_version: 'one',
      workspace_id: 'context',
      project_id: 'context',
      generation: 'context',
      binding_revision: 'context',
      binding_digest: 'context',
      lease_number: 'context',
      agent_type: 'context',
      api_authority_epoch: 'context',
      attachment_id: 'context',
      runtime_epoch: 'context',
      protocol_id: 'context',
      crypto_envelope_version: 'context',
      runtime_host_installation_revision: 'context',
      auth_epoch: 'context',
      runtime_host_installation_id: 'context',
      noise_protocol: 'noise',
      ciphertext: 'b64_48',
      status: 'verified',
      transcript_context_hash: 'hex32',
    },
    '8': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      state: 'RUNNING',
      output_cursor: 'cursor',
      lease_expires_at: 'timestamp',
    },
    '14': {
      protocol_version: 'one',
      nonce: 'hex8',
      echoed_sent_at_monotonic_tick: 'u64',
    },
    '16': {
      protocol_version: 'one',
      state: 'exit_state',
      exit_code: 'nullable_exit_code',
    },
    '17': {
      protocol_version: 'one',
      from_cursor: 'cursor',
      to_cursor: 'u64_zero',
      reason: 'gap_reason',
    },
    '18': {
      protocol_version: 'one',
      runtime_input_hop_sequence: 'u64',
      crypto_sequence: 'crypto',
      result: 'input_result',
      reason_code: 'nullable_input_reject',
      browser_input_hop_sequence: 'u64',
    },
    '19': {
      protocol_version: 'one',
      code: 'error',
      retryable: 'bool',
      request_id: 'nullable_wreq',
    },
    '20': {
      protocol_version: 'one',
      code: 'close',
      workspace_state_at_close: 'state',
    },
    '21': {
      protocol_version: 'one',
      workspace_id: 'aws',
      project_id: 'prj',
      agent_type: 'agent',
      generation: 'u64',
      state: 'state',
      reason_code: 'nullable_error',
    },
    '26': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
      acknowledged_hop_sequence: 'u64',
      requested_columns: 'columns',
      requested_rows: 'rows',
      effective_columns: 'nullable_columns',
      effective_rows: 'nullable_rows',
      result: 'resize_result',
      reason_code: 'nullable_resize_reject',
    },
    '27': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
      acknowledged_hop_sequence: 'u64',
      result: 'detach_result',
      cleanup_state: 'cleanup',
      reason_code: 'nullable_detach_reject',
    },
  },
  'api-to-runtime': {
    '2': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      resume_cursor: 'nullable_cursor',
      previous_runtime_epoch: 'nullable_u64',
      capability: 'hex32',
    },
    '3': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      noise_protocol: 'noise',
      crypto_envelope_version: 'one',
      browser_ephemeral_public_key: 'b64_32',
      noise_message_1: 'b64_32',
    },
    '5': {
      protocol_version: 'one',
      workspace_id: 'context',
      project_id: 'context',
      generation: 'context',
      binding_revision: 'context',
      binding_digest: 'context',
      lease_number: 'context',
      agent_type: 'context',
      api_authority_epoch: 'context',
      attachment_id: 'context',
      runtime_epoch: 'context',
      protocol_id: 'context',
      crypto_envelope_version: 'context',
      runtime_host_installation_revision: 'context',
      auth_epoch: 'context',
      runtime_host_installation_id: 'context',
      noise_protocol: 'noise',
      ciphertext: 'b64_48',
    },
    '11': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
      columns: 'columns',
      rows: 'rows',
    },
    '12': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
      sent_at_monotonic_tick: 'u64',
    },
    '13': {
      protocol_version: 'one',
      nonce: 'hex8',
      sent_at_monotonic_tick: 'u64',
    },
    '14': {
      protocol_version: 'one',
      nonce: 'hex8',
      echoed_sent_at_monotonic_tick: 'u64',
    },
    '15': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
    },
    '20': {
      protocol_version: 'one',
      code: 'close',
      workspace_state_at_close: 'state',
    },
    '22': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
    },
    '24': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      admission_fence: 'hex32',
    },
  },
  'runtime-to-api': {
    '4': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      noise_protocol: 'noise',
      crypto_envelope_version: 'one',
      runtime_attestation_x25519_fingerprint: 'hex32',
      runtime_ephemeral_public_key: 'b64_32',
      noise_message_2: 'b64_128',
    },
    '6': {
      protocol_version: 'one',
      workspace_id: 'context',
      project_id: 'context',
      generation: 'context',
      binding_revision: 'context',
      binding_digest: 'context',
      lease_number: 'context',
      agent_type: 'context',
      api_authority_epoch: 'context',
      attachment_id: 'context',
      runtime_epoch: 'context',
      protocol_id: 'context',
      crypto_envelope_version: 'context',
      runtime_host_installation_revision: 'context',
      auth_epoch: 'context',
      runtime_host_installation_id: 'context',
      noise_protocol: 'noise',
      ciphertext: 'b64_48',
      status: 'verified',
      transcript_context_hash: 'hex32',
    },
    '7': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      state: 'RUNNING',
      output_cursor: 'cursor',
      input_limit: 'input_limit',
      output_limit: 'output_limit',
    },
    '12': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
      sent_at_monotonic_tick: 'u64',
    },
    '13': {
      protocol_version: 'one',
      nonce: 'hex8',
      sent_at_monotonic_tick: 'u64',
    },
    '14': {
      protocol_version: 'one',
      nonce: 'hex8',
      echoed_sent_at_monotonic_tick: 'u64',
    },
    '16': {
      protocol_version: 'one',
      state: 'exit_state',
      exit_code: 'nullable_exit_code',
    },
    '17': {
      protocol_version: 'one',
      from_cursor: 'cursor',
      to_cursor: 'u64_zero',
      reason: 'gap_reason',
    },
    '18': {
      protocol_version: 'one',
      runtime_input_hop_sequence: 'u64',
      crypto_sequence: 'crypto',
      result: 'input_result',
      reason_code: 'nullable_input_reject',
    },
    '19': {
      protocol_version: 'one',
      code: 'error',
      retryable: 'bool',
      request_id: 'nullable_wreq',
    },
    '20': {
      protocol_version: 'one',
      code: 'close',
      workspace_state_at_close: 'state',
    },
    '21': {
      protocol_version: 'one',
      workspace_id: 'aws',
      project_id: 'prj',
      agent_type: 'agent',
      generation: 'u64',
      state: 'state',
      reason_code: 'nullable_error',
      runtime_epoch: 'u64',
    },
    '23': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      state: 'RUNNING',
      output_cursor: 'cursor',
      admission_fence: 'hex32',
    },
    '25': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      result: 'commit_result',
      reason_code: 'nullable_reject',
    },
    '26': {
      protocol_version: 'one',
      attachment_id: 'att',
      lease_number: 'u64',
      acknowledged_hop_sequence: 'u64',
      requested_columns: 'columns',
      requested_rows: 'rows',
      effective_columns: 'nullable_columns',
      effective_rows: 'nullable_rows',
      result: 'resize_result',
      reason_code: 'nullable_resize_reject',
    },
    '27': {
      protocol_version: 'one',
      workspace_id: 'admission',
      project_id: 'admission',
      generation: 'admission',
      binding_revision: 'admission',
      binding_digest: 'admission',
      lease_number: 'admission',
      agent_type: 'admission',
      api_authority_epoch: 'admission',
      attachment_id: 'admission',
      mode: 'admission',
      runtime_host_installation_revision: 'admission',
      auth_epoch: 'admission',
      runtime_host_installation_id: 'admission',
      runtime_epoch: 'u64',
      acknowledged_hop_sequence: 'u64',
      result: 'detach_result',
      cleanup_state: 'cleanup',
      reason_code: 'nullable_detach_reject',
    },
  },
}
export const WORKSPACE_STATES = Object.freeze([
  'BROKEN',
  'COLLISION',
  'EXITED',
  'LOGIN_REQUIRED',
  'MISSING',
  'NEEDS_INTERACTION',
  'RUNNING',
  'STARTING',
  'STOPPED',
  'STOPPING',
  'TRUST_REQUIRED',
  'UNKNOWN',
])
export const ERROR_CODES = Object.freeze([
  'ADMITTED_DELIVERY_FAILED',
  'ATTACHMENT_NOT_READY',
  'ATTACHMENT_PREPARE_REPLAY',
  'ATTACHMENT_STALE',
  'ATTACHMENT_TICKET_EXPIRED',
  'ATTACHMENT_TICKET_RATE_LIMITED',
  'ATTACHMENT_TICKET_REPLAYED',
  'ATTACHMENT_TICKET_UNAVAILABLE',
  'BINDING_BOOTSTRAP_REQUIRED',
  'CODEX_REMOTE_CONFLICT',
  'CONTROL_RATE_LIMITED',
  'DETACH_FAILED',
  'DETACH_IN_PROGRESS',
  'INPUT_RATE_LIMITED',
  'INPUT_WRITE_UNCERTAIN',
  'INTERNAL_BOUNDED',
  'KEY_CONFIRM_FAILED',
  'OUTPUT_BACKPRESSURE',
  'PROJECT_IDENTITY_CHANGED',
  'PROJECT_PATH_UNSUPPORTED',
  'PROJECT_RUNTIME_ACTIVE',
  'PROTOCOL_INVALID',
  'RANDOMNESS_UNAVAILABLE',
  'RECONCILIATION_REQUIRED',
  'RESIZE_FAILED',
  'RUNTIME_INSTALLATION_MISMATCH',
  'RUNTIME_INSTALLATION_UNTRUSTED',
  'RUNTIME_PEER_FORBIDDEN',
  'RUNTIME_UNAVAILABLE',
  'SEQUENCE_EXHAUSTED',
  'SERVICE_SHUTDOWN',
  'STOP_TIMEOUT',
  'STREAM_CRYPTO_FAILURE',
  'TERMINAL_PARSE_LIMIT',
  'WAW_CGROUP_UNTRUSTED',
  'WAW_SOCKET_PROVENANCE_INVALID',
  'WAW_SOCKET_SET_INCOMPLETE',
  'WAW_TMP_UNTRUSTED',
  'WORKSPACE_AUTH_CHECK_REQUIRED',
  'WORKSPACE_AUTH_REQUIRED',
  'WORKSPACE_AUTH_STATUS_UNKNOWN',
  'WORKSPACE_COLLISION',
  'WORKSPACE_EXECUTABLE_UNSUPPORTED',
  'WORKSPACE_EXITED',
  'WORKSPACE_MISSING',
  'WORKSPACE_NOT_FOUND',
  'WORKSPACE_NOT_READY',
  'WORKSPACE_NOT_RUNNING',
  'WORKSPACE_RESOURCE_LIMITED',
  'WORKSPACE_START_IN_PROGRESS',
  'WORKSPACE_STOPPED',
  'WORKSPACE_TRUST_REQUIRED',
  'WORKSPACE_WRITER_BUSY',
])
const RUNTIME_CLOSE = Object.freeze([
  'ADMISSION_TIMEOUT',
  'ATTACHMENT_STALE',
  'CONTROL_RATE_LIMITED',
  'OUTPUT_BACKPRESSURE',
  'PROTOCOL_INVALID',
  'RUNTIME_RESTART',
  'RUNTIME_UNAVAILABLE',
  'SEQUENCE_EXHAUSTED',
  'TERMINAL_PARSE_LIMIT',
  'WORKSPACE_EXITED',
  'WORKSPACE_STOPPED',
])
const API_CLOSE = Object.freeze([
  'ADMISSION_TIMEOUT',
  'ATTACHMENT_STALE',
  'AUTH_EPOCH_CHANGED',
  'DETACHED',
  'LEASE_STALE',
  'OUTPUT_BACKPRESSURE',
  'PROTOCOL_INVALID',
  'RUNTIME_UNAVAILABLE',
  'SERVICE_SHUTDOWN',
  'SESSION_REVOKED',
  'TERMINAL_PARSE_LIMIT',
])
const INTERNAL_CLOSE = Object.freeze([
  'ADMISSION_TIMEOUT',
  'ATTACHMENT_STALE',
  'AUTH_EPOCH_CHANGED',
  'CONTROL_RATE_LIMITED',
  'DETACHED',
  'INTERNAL_BOUNDED',
  'LEASE_STALE',
  'OUTPUT_BACKPRESSURE',
  'PROTOCOL_INVALID',
  'RUNTIME_UNAVAILABLE',
  'SERVICE_SHUTDOWN',
  'SESSION_REVOKED',
  'TERMINAL_PARSE_LIMIT',
])
const REJECT = Object.freeze([
  'ATTACHMENT_STALE',
  'RECONCILIATION_REQUIRED',
  'WORKSPACE_EXITED',
  'WORKSPACE_NOT_RUNNING',
  'WORKSPACE_STOPPED',
])
const RESIZE_REJECT = Object.freeze([
  'ATTACHMENT_STALE',
  'CONTROL_RATE_LIMITED',
  'RESIZE_FAILED',
  'WORKSPACE_EXITED',
  'WORKSPACE_NOT_RUNNING',
  'WORKSPACE_STOPPED',
])
const DETACH_REJECT = Object.freeze([
  'ATTACHMENT_STALE',
  'DETACH_FAILED',
  'RECONCILIATION_REQUIRED',
  'WORKSPACE_EXITED',
  'WORKSPACE_NOT_RUNNING',
  'WORKSPACE_STOPPED',
])
const KEY_TYPES: readonly number[] = [3, 4, 5, 6]
export class WireError extends Error {
  constructor() {
    super('PROTOCOL_INVALID')
    this.name = 'WireError'
  }
}
function fail(): never {
  throw new WireError()
}
const validLeg = (leg: unknown): leg is Leg =>
  typeof leg === 'string' && Object.values(Leg).includes(leg as Leg)
function profile(kind: unknown, leg: unknown): asserts kind is FrameType {
  if (
    !validLeg(leg) ||
    typeof kind !== 'number' ||
    !Number.isInteger(kind) ||
    !ALLOWED[leg].includes(kind)
  )
    fail()
}
const scalarString = (v: unknown): string =>
  typeof v === 'string' ? v : fail()
const uint = (v: unknown, min = 1n, max = U64_MAX): string => {
  const s = scalarString(v)
  if (!/^(0|[1-9][0-9]{0,19})$/.test(s) || BigInt(s) < min || BigInt(s) > max)
    fail()
  return s
}
function scalar(value: unknown, rule: string, leg: Leg): void {
  if (rule === 'admission' || rule === 'context') return
  if (rule.startsWith('nullable_')) {
    if (value === null) return
    rule = rule.slice(9)
  }
  if (['u64', 'crypto', 'cursor', 'u64_zero'].includes(rule)) {
    uint(
      value,
      ['cursor', 'u64_zero'].includes(rule) ? 0n : 1n,
      ['cursor', 'crypto'].includes(rule) ? U64_MAX - 1n : U64_MAX,
    )
    return
  }
  const bounds: Record<string, readonly [number, number]> = {
    one: [1, 1],
    input_limit: [INPUT_LIMIT, INPUT_LIMIT],
    output_limit: [OUTPUT_LIMIT, OUTPUT_LIMIT],
    columns: [8, 240],
    rows: [1, 200],
    exit_code: [-128, 255],
  }
  if (rule in bounds) {
    const [lo, hi] = bounds[rule]
    if (
      typeof value !== 'number' ||
      !Number.isSafeInteger(value) ||
      value < lo ||
      value > hi
    )
      fail()
    return
  }
  if (rule === 'bool') {
    if (typeof value !== 'boolean') fail()
    return
  }
  const s = scalarString(value)
  if (['att', 'aws', 'prj', 'wat', 'wreq'].includes(rule)) {
    if (!new RegExp(`^${rule}_[a-f0-9]{32}$`).test(s)) fail()
    return
  }
  if (rule === 'hex8' || rule === 'hex32') {
    if (!new RegExp(`^[a-f0-9]{${rule === 'hex8' ? 16 : 64}}$`).test(s)) fail()
    return
  }
  if (rule.startsWith('b64_')) {
    const size = Number(rule.slice(4)),
      remainder = size % 3
    if (
      s.length !== Math.ceil((size * 8) / 6) ||
      !/^[A-Za-z0-9_-]+$/.test(s) ||
      (remainder !== 0 &&
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'.indexOf(
          s.at(-1)!,
        ) %
          (remainder === 1 ? 16 : 4) !==
          0)
    )
      fail()
    return // Alphabet, length and unused bits only; no Noise body decode.
  }
  if (rule === 'timestamp') {
    const match =
      /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.([0-9]{6})Z$/.exec(
        s,
      )
    if (!match) fail()
    const [year, month, day, hour, minute, second] = match
      .slice(1, 7)
      .map(Number)
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (
      year < 1 ||
      month < 1 ||
      month > 12 ||
      day < 1 ||
      day > days[month - 1] ||
      hour > 23 ||
      minute > 59 ||
      second > 59
    )
      fail()
    return
  }
  const enums: Record<string, readonly string[]> = {
    noise: ['Noise_NX_25519_AESGCM_SHA256'],
    verified: ['verified'],
    RUNNING: ['RUNNING'],
    agent: ['claude', 'codex'],
    commit_result: ['committed', 'rejected'],
    resize_result: ['applied', 'rejected'],
    detach_result: ['detached', 'already_detached', 'rejected'],
    cleanup: ['ATTACH_PTY_CLOSED', 'ATTACH_PTY_CLOSE_UNCERTAIN'],
    exit_state: [
      'EXITED',
      'STOPPED',
      'MISSING',
      'COLLISION',
      'BROKEN',
      'UNKNOWN',
    ],
    gap_reason: [
      'baseline_redraw',
      'ring_overflow',
      'cursor_expired',
      'slow_client',
    ],
    input_result: ['accepted', 'written_to_pty', 'write_uncertain', 'rejected'],
    error: ERROR_CODES,
    state: WORKSPACE_STATES,
    reject: REJECT,
    resize_reject: RESIZE_REJECT,
    detach_reject: DETACH_REJECT,
    input_reject: [...REJECT, 'INPUT_RATE_LIMITED', 'INPUT_WRITE_UNCERTAIN'],
    close:
      leg === AR
        ? INTERNAL_CLOSE
        : leg === RA
          ? RUNTIME_CLOSE
          : [...RUNTIME_CLOSE, ...API_CLOSE],
  }
  if (!enums[rule]?.includes(s)) fail()
}

export interface ValidationBinding {
  /** Independently bound data; this function neither learns nor authenticates it. */
  readonly admission?: AdmissionTuple
  readonly runtimeEpoch?: string
  readonly trustedContext?: boolean
}
export type WireRecord = Readonly<Record<string, unknown>>
/** Syntax/context checks only, not ACK maps, ping nonce matching, lease or process authority. */
export function validatePayload(
  frameType: FrameType,
  leg: Leg,
  payload: unknown,
  binding: ValidationBinding = {},
): WireRecord | Uint8Array {
  try {
    profile(frameType, leg)
    const trusted =
      binding.trustedContext === undefined ? true : binding.trustedContext
    if (typeof trusted !== 'boolean') fail()
    if (frameType === 9 || frameType === 10) {
      if (
        !(payload instanceof Uint8Array) ||
        payload.constructor !== Uint8Array
      )
        fail()
      const env = decodeAwce(payload),
        direction = frameType === 9 ? 1 : 2,
        ceiling = frameType === 9 ? INPUT_LIMIT : OUTPUT_LIMIT
      if (
        env.direction_id !== direction ||
        env.ciphertext_length > ceiling + 16
      )
        fail()
      return new Uint8Array(payload)
    }
    const schema = SCHEMAS[leg][frameType],
      r = exactRecord(payload, Object.keys(schema))
    for (const [key, rule] of Object.entries(schema)) scalar(r[key], rule, leg)
    if (ADMISSION_KEYS.every((key) => Object.hasOwn(r, key)))
      validateAdmission(
        Object.fromEntries(ADMISSION_KEYS.map((key) => [key, r[key]])),
      )
    else if (CONTEXT_KEYS.every((key) => Object.hasOwn(r, key)))
      validateContext(
        Object.fromEntries(CONTEXT_KEYS.map((key) => [key, r[key]])),
      )
    if (binding.admission !== undefined) {
      const bound = validateAdmission(binding.admission)
      for (const key of ADMISSION_KEYS)
        if (Object.hasOwn(r, key) && r[key] !== bound[key]) fail()
    }
    if (binding.runtimeEpoch !== undefined) {
      const epoch = validateU64(binding.runtimeEpoch)
      if (Object.hasOwn(r, 'runtime_epoch') && r.runtime_epoch !== epoch) fail()
    }
    if (frameType === 19 && trusted && r.request_id === null) fail()
    if (frameType === 26) {
      if (r.result === 'applied') {
        if (
          r.reason_code !== null ||
          r.effective_columns !== r.requested_columns ||
          r.effective_rows !== r.requested_rows
        )
          fail()
      } else if (
        r.reason_code === null ||
        r.effective_columns !== null ||
        r.effective_rows !== null
      )
        fail()
    } else if (frameType === 27) {
      const positive = r.result !== 'rejected'
      if (
        (r.reason_code === null) !== positive ||
        r.cleanup_state !==
          (positive ? 'ATTACH_PTY_CLOSED' : 'ATTACH_PTY_CLOSE_UNCERTAIN')
      )
        fail()
    } else if (frameType === 25) {
      if ((r.result === 'committed') !== (r.reason_code === null)) fail()
    } else if (frameType === 18) {
      if (r.result === 'accepted' || r.result === 'written_to_pty') {
        if (r.reason_code !== null) fail()
      } else if (r.result === 'write_uncertain') {
        if (r.reason_code !== 'INPUT_WRITE_UNCERTAIN') fail()
      } else if (
        ![...REJECT, 'INPUT_RATE_LIMITED'].includes(r.reason_code as string)
      )
        fail()
    } else if (frameType === 17) {
      const from = BigInt(r.from_cursor as string),
        to = BigInt(r.to_cursor as string)
      if (r.reason === 'baseline_redraw') {
        if (from !== 0n || to !== 0n) fail()
      } else if (from < 1n || to <= from) fail()
    }
    return Object.freeze(r)
  } catch {
    throw new WireError()
  }
}

/** Exact bounded integer conversion of RFC8259 Number spellings without binary64 rounding. */
function exactInteger(token: string): number {
  const m = /^(-?)([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?$/.exec(token)
  if (!m) fail()
  const fraction = m[3] ?? '',
    digits = (m[2] + fraction).replace(/^0+/, '')
  if (digits === '') return 0
  const shift = BigInt(m[4] ?? '0') - BigInt(fraction.length)
  let integral: string
  if (shift >= 0n) {
    if (BigInt(digits.length) + shift > 5n) fail()
    integral = digits + '0'.repeat(Number(shift))
  } else {
    const trim = -shift
    if (trim >= BigInt(digits.length) || trim > 4096n) fail()
    const n = Number(trim)
    if (!/^0+$/.test(digits.slice(-n))) fail()
    integral = digits.slice(0, -n)
  }
  if (integral.length > 5) fail()
  const result = Number((m[1] ?? '') + integral)
  if (!Number.isSafeInteger(result) || Math.abs(result) > 32768) fail()
  return result
}
function strictJson(payload: Uint8Array): WireRecord {
  if (payload.length < 1 || payload.length > MAX_CONTROL_BYTES) fail()
  const text = new TextDecoder('utf-8', {
    fatal: true,
    ignoreBOM: true,
  }).decode(payload)
  let pos = 0,
    keys = 0
  const space = () => {
    while (/[\x20\t\r\n]/.test(text[pos] ?? '!')) pos++
  }
  function string(): string {
    const start = pos++
    if (text[start] !== '"') fail()
    while (pos < text.length) {
      const c = text[pos++]
      if (c === '\\') {
        pos++
        continue
      }
      if (c === '"') {
        const s = JSON.parse(text.slice(start, pos)) as string
        for (const char of s) {
          const cp = char.codePointAt(0)!
          if (cp >= 0xd800 && cp <= 0xdfff) fail()
        }
        return s
      }
    }
    return fail()
  }
  function value(depth: number, key?: string): unknown {
    space()
    if (depth > 16) fail()
    const c = text[pos]
    if (c === '"') return string()
    if (c === '{') {
      if (depth === 16) fail()
      pos++
      space()
      const r: Record<string, unknown> = Object.create(null) as Record<
        string,
        unknown
      >
      if (text[pos] === '}') {
        pos++
        return r
      }
      while (true) {
        space()
        const k = string()
        if (++keys > 64 || Object.hasOwn(r, k)) fail()
        space()
        if (text[pos++] !== ':') fail()
        r[k] = value(depth + 1, k)
        space()
        const delimiter = text[pos++]
        if (delimiter === '}') return r
        if (delimiter !== ',') fail()
      }
    }
    if (c === '[') {
      if (depth === 16) fail()
      pos++
      space()
      const a: unknown[] = []
      if (text[pos] === ']') {
        pos++
        return a
      }
      while (true) {
        a.push(value(depth + 1))
        space()
        const delimiter = text[pos++]
        if (delimiter === ']') return a
        if (delimiter !== ',') fail()
      }
    }
    for (const [literal, result] of [
      ['true', true],
      ['false', false],
      ['null', null],
    ] as const) {
      if (text.startsWith(literal, pos)) {
        pos += literal.length
        return result
      }
    }
    const token = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(
      text.slice(pos),
    )?.[0]
    if (!token) fail()
    pos += token.length
    if (
      (key === 'protocol_version' || key === 'crypto_envelope_version') &&
      token !== '1'
    )
      fail()
    return exactInteger(token)
  }
  const parsed = value(0)
  space()
  if (
    pos !== text.length ||
    !parsed ||
    typeof parsed !== 'object' ||
    Array.isArray(parsed)
  )
    fail()
  const record = parsed as Record<string, unknown>
  for (const item of Object.values(record))
    if (item !== null && !['string', 'number', 'boolean'].includes(typeof item))
      fail()
  return record
}

/** Private copied buffers keep normal inspection/JSON serialization free of bearers. */
export class WireFrame {
  readonly frameType: FrameType
  readonly leg: Leg
  readonly hopSequence: bigint
  readonly replay: boolean
  readonly #payload: Uint8Array
  readonly #json: WireRecord | null
  readonly #wire: Uint8Array
  constructor(
    frameType: FrameType,
    leg: Leg,
    hopSequence: bigint,
    payload: Uint8Array,
    json: WireRecord | null,
    wire: Uint8Array,
    replay = false,
  ) {
    this.frameType = frameType
    this.leg = leg
    this.hopSequence = hopSequence
    this.#payload = new Uint8Array(payload)
    this.#json = json === null ? null : Object.freeze({ ...json })
    this.#wire = new Uint8Array(wire)
    this.replay = replay
    Object.freeze(this)
  }
  get payload(): Uint8Array {
    return new Uint8Array(this.#payload)
  }
  get jsonPayload(): WireRecord | null {
    return this.#json === null ? null : Object.freeze({ ...this.#json })
  }
  get wireBytes(): Uint8Array {
    return new Uint8Array(this.#wire)
  }
  toString(): string {
    return `WireFrame(frameType=${this.frameType}, leg=${this.leg}, hopSequence=${this.hopSequence}, payload=<redacted>)`
  }
  toJSON(): object {
    return {
      frameType: this.frameType,
      leg: this.leg,
      hopSequence: this.hopSequence.toString(),
      payload: '<redacted>',
    }
  }
}

export function decodeWireFrame(
  raw: unknown,
  leg: Leg,
  binding: ValidationBinding = {},
): WireFrame {
  // Browser JS exposes no per-thread CPU clock: this elapsed-time ceiling is
  // deliberately more conservative than the protocol CPU ceiling.
  const start = performance.now()
  try {
    if (
      !(raw instanceof Uint8Array) ||
      raw.constructor !== Uint8Array ||
      raw.length < 24 ||
      raw.length > MAX_FRAME_BYTES
    )
      fail()
    const wire = new Uint8Array(raw),
      v = new DataView(wire.buffer),
      kind = v.getUint8(5)
    profile(kind, leg)
    if (
      v.getUint32(0) !== 0x41425753 ||
      v.getUint8(4) !== 1 ||
      v.getUint16(6) !== 0 ||
      v.getUint32(20) !== 0 ||
      v.getUint32(8) !== wire.length - 24 ||
      v.getBigUint64(12) === 0n
    )
      fail()
    const payload = wire.slice(24),
      opaque = kind === 9 || kind === 10,
      record = opaque ? null : strictJson(payload)
    const checked = validatePayload(kind, leg, record ?? payload, binding)
    if (!opaque && performance.now() - start > VALIDATION_MS) fail()
    return new WireFrame(
      kind,
      leg,
      v.getBigUint64(12),
      payload,
      checked instanceof Uint8Array ? null : checked,
      wire,
    )
  } catch {
    throw new WireError()
  }
}
function pack(kind: FrameType, payload: Uint8Array, hop: bigint): Uint8Array {
  if (typeof hop !== 'bigint' || hop < 1n || hop > U64_MAX) fail()
  const raw = new Uint8Array(24 + payload.length),
    v = new DataView(raw.buffer)
  v.setUint32(0, 0x41425753)
  v.setUint8(4, 1)
  v.setUint8(5, kind)
  v.setUint32(8, payload.length)
  v.setBigUint64(12, hop)
  raw.set(payload, 24)
  return raw
}
/** Origin construction only. Relay key frames with forwardWireFrame. */
export function encodeWireFrame(
  kind: FrameType,
  leg: Leg,
  payload: unknown,
  hop: bigint,
  binding: ValidationBinding = {},
): Uint8Array {
  try {
    const checked = validatePayload(kind, leg, payload, binding),
      encoded =
        checked instanceof Uint8Array
          ? checked
          : new TextEncoder().encode(JSON.stringify(checked))
    return decodeWireFrame(pack(kind, encoded, hop), leg, binding).wireBytes
  } catch {
    throw new WireError()
  }
}
/** Change only outer hop sequence for allowed key/terminal relay directions. */
export function forwardWireFrame(
  frame: WireFrame,
  leg: Leg,
  hop: bigint,
): Uint8Array {
  if (
    !(frame instanceof WireFrame) ||
    Object.getPrototypeOf(frame) !== WireFrame.prototype ||
    !((frame.leg === BA && leg === AR) || (frame.leg === RA && leg === AB)) ||
    ![...KEY_TYPES, 9, 10].includes(frame.frameType)
  )
    fail()
  return decodeWireFrame(pack(frame.frameType, frame.payload, hop), leg)
    .wireBytes
}
const sameBytes = (a: Uint8Array, b: Uint8Array): boolean =>
  a.length === b.length && a.every((v, i) => v === b[i])
const seenKey = (leg: Leg, kind: FrameType): string => `${leg}/${kind}`
/**
 * API/coordinator observation only. Never grants a writer or proves browser crypto
 * verification. Synchronous operations belong to one JS agent; this instance is
 * not shared mutable state across Workers. Pending exact relay bytes witness the
 * transcript only; real send queues and ACK lifecycle belong to the coordinator.
 */
export class WireSession {
  readonly #admission: AdmissionTuple
  readonly #context: HandshakeContext
  readonly #streamId: object
  readonly #started: bigint
  #lastNow: bigint
  readonly #next: Record<Leg, bigint> = {
    [BA]: 1n,
    [AB]: 1n,
    [AR]: 1n,
    [RA]: 1n,
  }
  readonly #seen = new Map<string, WireFrame>()
  readonly #terminal = new Set<Leg>()
  readonly #mustClose = new Set<Leg>()
  readonly #crypto: Record<Leg, bigint> = {
    [BA]: 1n,
    [AB]: 1n,
    [AR]: 1n,
    [RA]: 1n,
  }
  readonly #cursor: Record<Leg, bigint> = {
    [BA]: 0n,
    [AB]: 0n,
    [AR]: 0n,
    [RA]: 0n,
  }
  readonly #retries = new Set<string>()
  #detachAt: bigint | null = null
  readonly #detach = new Map<Leg, WireFrame>()
  #exits = new Map<Leg, WireFrame>()
  readonly #pending: Record<number, Uint8Array[]> = { 9: [], 10: [] }
  readonly #pendingBytes: Record<number, number> = { 9: 0, 10: 0 }
  #failed = false
  #closed = false
  constructor(
    admission: unknown,
    runtimeEpoch: unknown,
    options: { streamId: object; startedAt: bigint },
  ) {
    try {
      this.#admission = validateAdmission(admission)
      this.#context = deriveContext(admission, runtimeEpoch)
    } catch {
      throw new WireError()
    }
    if (
      !options ||
      typeof options.streamId !== 'object' ||
      options.streamId === null ||
      typeof options.startedAt !== 'bigint' ||
      options.startedAt < 0n
    )
      fail()
    this.#streamId = options.streamId
    this.#started = this.#lastNow = options.startedAt
  }
  get closed(): boolean {
    return this.#closed
  }
  get failed(): boolean {
    return this.#failed
  }
  get admitted(): boolean {
    return this.#has(AB, 8) && !this.#failed && !this.#closed
  }
  get committed(): boolean {
    return this.#seen.get(seenKey(RA, 25))?.jsonPayload?.result === 'committed'
  }
  expectedSequence(leg: Leg): bigint {
    if (!validLeg(leg)) fail()
    return this.#next[leg]
  }
  close(): void {
    this.#closed = true
    this.#seen.clear()
    this.#detach.clear()
    this.#clearPending()
  }
  #has(leg: Leg, kind: FrameType): boolean {
    return this.#seen.has(seenKey(leg, kind))
  }
  #require(leg: Leg, kind: FrameType): WireFrame {
    return this.#seen.get(seenKey(leg, kind)) ?? fail()
  }
  #retry(frame: WireFrame, now: bigint): boolean {
    const key = seenKey(frame.leg, frame.frameType)
    let original = this.#seen.get(key)
    if (frame.frameType === 15 && frame.leg === AR) {
      original = this.#detach.get(AR)
      if (
        this.#detachAt === null ||
        now - this.#detachAt >= ADMISSION_NS ||
        this.#detach.has(RA)
      )
        fail()
    } else if (frame.frameType === 24 && frame.leg === AR) {
      if (this.#has(AB, 8) || this.#next[RA] > 6n || this.#next[AR] > 6n) fail()
    } else if (frame.frameType === 25 && frame.leg === RA) {
      if (!this.#retries.has(seenKey(AR, 24)) || this.#has(AB, 8)) fail()
    } else fail()
    if (
      this.#failed ||
      this.#retries.has(key) ||
      !original ||
      !sameBytes(original.wireBytes, frame.wireBytes)
    )
      fail()
    if (frame.frameType !== 15 && now - this.#started >= ADMISSION_NS) fail()
    this.#retries.add(key)
    return true
  }
  #order(frame: WireFrame): void {
    const { leg, frameType: kind } = frame
    const prerequisites: Record<string, readonly [Leg, FrameType]> = {
      [seenKey(BA, 3)]: [BA, 1],
      [seenKey(AR, 2)]: [BA, 3],
      [seenKey(AR, 3)]: [AR, 2],
      [seenKey(RA, 7)]: [AR, 3],
      [seenKey(RA, 4)]: [RA, 7],
      [seenKey(AB, 4)]: [RA, 4],
      [seenKey(BA, 5)]: [AB, 4],
      [seenKey(AR, 5)]: [BA, 5],
      [seenKey(RA, 6)]: [AR, 5],
      [seenKey(AB, 6)]: [RA, 6],
      [seenKey(AR, 22)]: [AB, 6],
      [seenKey(RA, 23)]: [AR, 22],
      [seenKey(AR, 24)]: [RA, 23],
      [seenKey(RA, 25)]: [AR, 24],
      [seenKey(AB, 8)]: [RA, 25],
    }
    const previous = prerequisites[seenKey(leg, kind)]
    if (previous) this.#require(...previous)
    if (KEY_TYPES.includes(kind) && (leg === AR || leg === AB)) {
      const source = leg === AR ? BA : RA
      if (!sameBytes(frame.payload, this.#require(source, kind).payload)) fail()
    }
    const r = frame.jsonPayload
    if (r === null) return
    if (kind === 2) {
      const hello = this.#require(BA, 1).jsonPayload
      if (
        !hello ||
        ['resume_cursor', 'previous_runtime_epoch'].some(
          (key) => r[key] !== hello[key],
        )
      )
        fail()
    }
    if (kind === 23 || kind === 8) {
      const hello = this.#require(RA, 7).jsonPayload
      if (!hello || r.output_cursor !== hello.output_cursor) fail()
    }
    if (kind === 24) {
      const ready = this.#require(RA, 23).jsonPayload
      if (!ready || r.admission_fence !== ready.admission_fence) fail()
    }
    if (kind === 8 && !this.committed) fail()
  }
  #clearPending(): void {
    this.#pending[9].length = this.#pending[10].length = 0
    this.#pendingBytes[9] = this.#pendingBytes[10] = 0
  }
  #relayCheck(frame: WireFrame): boolean {
    const kind = frame.frameType,
      source = frame.leg === (kind === 9 ? BA : RA),
      queue = this.#pending[kind]
    if (source) {
      const limit = kind === 9 || !this.#has(AB, 8) ? 65536 : 262144
      if (
        this.#pendingBytes[kind] + frame.wireBytes.length > limit ||
        queue.length >= 256
      )
        fail()
    } else if (!queue.length || !sameBytes(queue[0], frame.payload)) fail()
    return source
  }
  #phase(frame: WireFrame): void {
    const { leg, frameType: kind, hopSequence: seq } = frame
    if (this.#terminal.has(leg) || (this.#mustClose.has(leg) && kind !== 20))
      fail()
    if (this.#failed && ![21, 19, 20, 16].includes(kind)) fail()
    if (
      kind === 21 &&
      frame.jsonPayload?.state === 'RUNNING' &&
      (this.#failed || !this.#has(AB, 8))
    )
      fail()
    const handshake = HANDSHAKE[leg]
    if (seq <= BigInt(handshake.length)) {
      if (kind === handshake[Number(seq) - 1]) {
        if (this.#failed) fail()
        this.#order(frame)
        return
      }
      if (kind === 20 && leg === AR && this.#has(AR, 2)) return
      if (leg === RA) {
        if (seq <= 2n && kind === 19) {
          this.#require(AR, 3)
          return
        }
        if (seq >= 3n && [21, 19, 20].includes(kind)) {
          if (kind === 20 && !this.#mustClose.has(leg)) fail()
          return
        }
      }
      if (leg === AB && [19, 21, 20].includes(kind)) {
        if (kind === 19) return
        if (!this.#has(AB, 4) || (kind === 20 && !this.#mustClose.has(leg)))
          fail()
        return
      }
      fail()
    }
    if (kind === 16 && this.#failed) {
      const original = this.#exits.get(RA)?.jsonPayload,
        incoming = frame.jsonPayload
      if (
        leg !== AB ||
        !original ||
        !incoming ||
        this.#exits.has(leg) ||
        Object.keys(original).some((k) => original[k] !== incoming[k])
      )
        fail()
      return
    }
    if ([20, 19, 21].includes(kind) && this.#failed) return
    if (leg === BA || leg === AB) {
      if (!this.admitted) fail()
    } else if (!this.committed) fail()
    if (leg === AR && kind !== 20 && !this.admitted) fail()
    if (Object.values(HANDSHAKE).some((values) => values.includes(kind))) fail()
    if (this.#detach.size > 0 && ![15, 27, 20, 19, 21, 18, 16].includes(kind))
      fail()
    this.#order(frame)
    if (kind === 15) {
      if (this.#detach.has(leg) || (leg === AR && !this.#detach.has(BA))) fail()
    } else if (kind === 27) {
      const request = this.#detach.get(leg === RA ? AR : BA),
        r = frame.jsonPayload
      if (
        !request ||
        this.#detach.has(leg) ||
        !r ||
        r.acknowledged_hop_sequence !== request.hopSequence.toString()
      )
        fail()
      if (leg === AB) {
        const response = this.#detach.get(RA)?.jsonPayload
        if (
          !response ||
          ['result', 'cleanup_state', 'reason_code'].some(
            (key) => r[key] !== response[key],
          )
        )
          fail()
      }
    }
  }
  /** Invalid observation closes the validator; no authority state or I/O is changed. */
  accept(
    leg: Leg,
    raw: unknown,
    options: { streamId: object; now: bigint },
  ): WireFrame {
    try {
      if (
        this.#closed ||
        options.streamId !== this.#streamId ||
        typeof options.now !== 'bigint' ||
        options.now < this.#lastNow ||
        !validLeg(leg)
      )
        fail()
      const now = options.now
      if (!this.#has(AB, 8) && now - this.#started >= ADMISSION_NS) fail()
      const trusted = this.#has(AR, 2)
      const frame = decodeWireFrame(raw, leg, {
        admission: this.#admission,
        runtimeEpoch: this.#context.runtime_epoch,
        trustedContext: trusted,
      })
      if (frame.hopSequence !== this.#next[leg] && this.#retry(frame, now)) {
        this.#lastNow = now
        return new WireFrame(
          frame.frameType,
          leg,
          frame.hopSequence,
          frame.payload,
          frame.jsonPayload,
          frame.wireBytes,
          true,
        )
      }
      this.#phase(frame)
      const kind = frame.frameType,
        r = frame.jsonPayload
      if (kind === 9 || kind === 10) {
        const source = this.#relayCheck(frame)
        const envelope = decodeAwce(frame.payload),
          confirmation = this.#require(RA, 6).jsonPayload
        const hash = confirmation?.transcript_context_hash
        if (
          typeof hash !== 'string' ||
          !sameBytes(
            envelope.context_id,
            Uint8Array.from(
              hash
                .slice(0, 32)
                .match(/../g)!
                .map((v) => parseInt(v, 16)),
            ),
          ) ||
          envelope.crypto_sequence !== this.#crypto[leg]
        )
          fail()
        if (kind === 10 && envelope.stream_cursor <= this.#cursor[leg]) fail()
        if (source) {
          this.#pending[kind].push(frame.payload)
          this.#pendingBytes[kind] += frame.wireBytes.length
        } else {
          this.#pendingBytes[kind] -= 24 + this.#pending[kind].shift()!.length
        }
        this.#crypto[leg]++
        if (kind === 10) this.#cursor[leg] = envelope.stream_cursor
      }
      if (kind === 15) {
        this.#detach.set(leg, frame)
        if (leg === AR) this.#detachAt = now
      } else if (kind === 27) {
        this.#detach.set(leg, frame)
        this.#mustClose.add(leg)
      }
      if (kind === 20) {
        this.#terminal.add(leg)
        this.#failed = true
      } else if (kind === 16) {
        this.#exits.set(leg, frame)
        this.#mustClose.add(leg)
        this.#failed = true
      } else if (kind === 19 || kind === 21) {
        const nonfatalControlLimit =
          kind === 19 &&
          leg === AB &&
          this.#has(AB, 8) &&
          r?.code === 'CONTROL_RATE_LIMITED' &&
          r?.retryable === true
        if (
          (kind === 19 && !nonfatalControlLimit) ||
          (kind === 21 &&
            r?.state !== 'RUNNING' &&
            (!this.#has(AB, 8) || r?.state !== 'NEEDS_INTERACTION'))
        ) {
          this.#failed = true
          if (
            (leg === RA && frame.hopSequence <= 2n) ||
            (leg === AB && !this.#has(AB, 4))
          )
            this.#terminal.add(leg)
          else this.#mustClose.add(leg)
        }
      } else if (kind === 25 && r?.result === 'rejected') {
        this.#failed = true
        this.#mustClose.add(leg)
      }
      if (this.#failed) this.#clearPending()
      if (KEY_TYPES.includes(kind) || HANDSHAKE[leg].includes(kind))
        this.#seen.set(seenKey(leg, kind), frame)
      this.#next[leg]++
      this.#lastNow = now
      if (frame.hopSequence === U64_MAX) this.#terminal.add(leg)
      return frame
    } catch {
      this.close()
      throw new WireError()
    }
  }
}
