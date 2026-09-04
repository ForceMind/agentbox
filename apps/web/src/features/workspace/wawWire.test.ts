/** Synthetic public metadata vectors; no host or Noise qualification. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { encodeAwceHeader } from './awce'
import { deriveContext, type AdmissionTuple } from './wawCryptoContext'
import {
  FrameType as F,
  Leg,
  WireSession,
  WireError,
  validatePayload,
  decodeWireFrame,
  encodeWireFrame,
  forwardWireFrame,
  INPUT_LIMIT,
  OUTPUT_LIMIT,
  type WireRecord,
} from './wawWire'
// Unit tests use an explicit scheduler clock; GC/runner pauses are not protocol
// fixtures. The deadline rejection is separately tested with advancing readings.
beforeEach(() => {
  vi.spyOn(performance, 'now').mockReturnValue(0)
})
afterEach(() => {
  vi.restoreAllMocks()
})
const BA = Leg.BROWSER_TO_API,
  AB = Leg.API_TO_BROWSER,
  AR = Leg.API_TO_RUNTIME,
  RA = Leg.RUNTIME_TO_API
const A: AdmissionTuple = {
  attachment_id: 'att_11111111111111111111111111111111',
  workspace_id: 'aws_22222222222222222222222222222222',
  project_id: 'prj_33333333333333333333333333333333',
  agent_type: 'codex',
  runtime_host_installation_id: 'wri_44444444444444444444444444444444',
  runtime_host_installation_revision: '18446744073709551615',
  auth_epoch: '2',
  api_authority_epoch: '3',
  lease_number: '4',
  generation: '5',
  binding_revision: '6',
  mode: 'writer',
  binding_digest:
    '5555555555555555555555555555555555555555555555555555555555555555',
}
const EPOCH = '18446744073709551615'
const C = deriveContext(A, EPOCH)
const PROFILES: Record<Leg, readonly F[]> = {
  'browser-to-api': [1, 3, 5, 9, 11, 12, 13, 15],
  'api-to-browser': [4, 6, 8, 10, 14, 16, 17, 18, 19, 20, 21, 26, 27],
  'api-to-runtime': [2, 3, 5, 9, 11, 12, 13, 14, 15, 20, 22, 24],
  'runtime-to-api': [
    4, 6, 7, 10, 12, 13, 14, 16, 17, 18, 19, 20, 21, 23, 25, 26, 27,
  ],
}
// Closed direction-specific examples transcribed from the accepted wire tables.
const FIXTURES: Record<Leg, Record<number, WireRecord>> = {
  'browser-to-api': {
    '1': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      resume_cursor: null,
      previous_runtime_epoch: null,
      ticket: 'wat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    },
    '3': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      crypto_envelope_version: 1,
      browser_ephemeral_public_key:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
      noise_message_1: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    },
    '5': {
      protocol_version: 1,
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      auth_epoch: '2',
      workspace_id: 'aws_22222222222222222222222222222222',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      project_id: 'prj_33333333333333333333333333333333',
      binding_revision: '6',
      runtime_host_installation_revision: '18446744073709551615',
      attachment_id: 'att_11111111111111111111111111111111',
      generation: '5',
      lease_number: '4',
      api_authority_epoch: '3',
      protocol_id: 'agentbox-waw/v1',
      crypto_envelope_version: 1,
      runtime_epoch: '18446744073709551615',
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      ciphertext:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    },
    '11': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
      columns: 80,
      rows: 24,
    },
    '12': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
      sent_at_monotonic_tick: '18446744073709551615',
    },
    '13': {
      protocol_version: 1,
      nonce: '9999999999999999',
      sent_at_monotonic_tick: '1',
    },
    '15': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
    },
  },
  'api-to-browser': {
    '4': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      crypto_envelope_version: 1,
      runtime_attestation_x25519_fingerprint:
        '7777777777777777777777777777777777777777777777777777777777777777',
      runtime_ephemeral_public_key:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
      noise_message_2:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    },
    '6': {
      protocol_version: 1,
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      auth_epoch: '2',
      workspace_id: 'aws_22222222222222222222222222222222',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      project_id: 'prj_33333333333333333333333333333333',
      binding_revision: '6',
      runtime_host_installation_revision: '18446744073709551615',
      attachment_id: 'att_11111111111111111111111111111111',
      generation: '5',
      lease_number: '4',
      api_authority_epoch: '3',
      protocol_id: 'agentbox-waw/v1',
      crypto_envelope_version: 1,
      runtime_epoch: '18446744073709551615',
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      ciphertext:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
      status: 'verified',
      transcript_context_hash:
        '6666666666666666666666666666666666666666666666666666666666666666',
    },
    '8': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      state: 'RUNNING',
      output_cursor: '0',
      lease_expires_at: '2030-02-28T12:30:59.123456Z',
    },
    '14': {
      protocol_version: 1,
      nonce: '9999999999999999',
      echoed_sent_at_monotonic_tick: '1',
    },
    '16': { protocol_version: 1, state: 'EXITED', exit_code: -128 },
    '17': {
      protocol_version: 1,
      from_cursor: '1',
      to_cursor: '18446744073709551615',
      reason: 'ring_overflow',
    },
    '18': {
      protocol_version: 1,
      runtime_input_hop_sequence: '6',
      crypto_sequence: '1',
      result: 'accepted',
      reason_code: null,
      browser_input_hop_sequence: '4',
    },
    '19': {
      protocol_version: 1,
      code: 'PROTOCOL_INVALID',
      retryable: false,
      request_id: 'wreq_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    },
    '20': {
      protocol_version: 1,
      code: 'ATTACHMENT_STALE',
      workspace_state_at_close: 'RUNNING',
    },
    '21': {
      protocol_version: 1,
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      generation: '5',
      state: 'RUNNING',
      reason_code: null,
    },
    '26': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
      acknowledged_hop_sequence: '6',
      requested_columns: 80,
      requested_rows: 24,
      effective_columns: 80,
      effective_rows: 24,
      result: 'applied',
      reason_code: null,
    },
    '27': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
      acknowledged_hop_sequence: '6',
      result: 'detached',
      cleanup_state: 'ATTACH_PTY_CLOSED',
      reason_code: null,
    },
  },
  'api-to-runtime': {
    '2': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      resume_cursor: null,
      previous_runtime_epoch: null,
      capability:
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    },
    '3': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      crypto_envelope_version: 1,
      browser_ephemeral_public_key:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
      noise_message_1: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    },
    '5': {
      protocol_version: 1,
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      auth_epoch: '2',
      workspace_id: 'aws_22222222222222222222222222222222',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      project_id: 'prj_33333333333333333333333333333333',
      binding_revision: '6',
      runtime_host_installation_revision: '18446744073709551615',
      attachment_id: 'att_11111111111111111111111111111111',
      generation: '5',
      lease_number: '4',
      api_authority_epoch: '3',
      protocol_id: 'agentbox-waw/v1',
      crypto_envelope_version: 1,
      runtime_epoch: '18446744073709551615',
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      ciphertext:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    },
    '11': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
      columns: 80,
      rows: 24,
    },
    '12': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
      sent_at_monotonic_tick: '18446744073709551615',
    },
    '13': {
      protocol_version: 1,
      nonce: '9999999999999999',
      sent_at_monotonic_tick: '1',
    },
    '14': {
      protocol_version: 1,
      nonce: '9999999999999999',
      echoed_sent_at_monotonic_tick: '1',
    },
    '15': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
    },
    '20': {
      protocol_version: 1,
      code: 'ATTACHMENT_STALE',
      workspace_state_at_close: 'RUNNING',
    },
    '22': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
    },
    '24': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      admission_fence:
        '8888888888888888888888888888888888888888888888888888888888888888',
    },
  },
  'runtime-to-api': {
    '4': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      crypto_envelope_version: 1,
      runtime_attestation_x25519_fingerprint:
        '7777777777777777777777777777777777777777777777777777777777777777',
      runtime_ephemeral_public_key:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
      noise_message_2:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    },
    '6': {
      protocol_version: 1,
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      auth_epoch: '2',
      workspace_id: 'aws_22222222222222222222222222222222',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      project_id: 'prj_33333333333333333333333333333333',
      binding_revision: '6',
      runtime_host_installation_revision: '18446744073709551615',
      attachment_id: 'att_11111111111111111111111111111111',
      generation: '5',
      lease_number: '4',
      api_authority_epoch: '3',
      protocol_id: 'agentbox-waw/v1',
      crypto_envelope_version: 1,
      runtime_epoch: '18446744073709551615',
      noise_protocol: 'Noise_NX_25519_AESGCM_SHA256',
      ciphertext:
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
      status: 'verified',
      transcript_context_hash:
        '6666666666666666666666666666666666666666666666666666666666666666',
    },
    '7': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      state: 'RUNNING',
      output_cursor: '0',
      input_limit: 16384,
      output_limit: 32768,
    },
    '12': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
      sent_at_monotonic_tick: '18446744073709551615',
    },
    '13': {
      protocol_version: 1,
      nonce: '9999999999999999',
      sent_at_monotonic_tick: '1',
    },
    '14': {
      protocol_version: 1,
      nonce: '9999999999999999',
      echoed_sent_at_monotonic_tick: '1',
    },
    '16': { protocol_version: 1, state: 'EXITED', exit_code: -128 },
    '17': {
      protocol_version: 1,
      from_cursor: '1',
      to_cursor: '18446744073709551615',
      reason: 'ring_overflow',
    },
    '18': {
      protocol_version: 1,
      runtime_input_hop_sequence: '6',
      crypto_sequence: '1',
      result: 'accepted',
      reason_code: null,
    },
    '19': {
      protocol_version: 1,
      code: 'PROTOCOL_INVALID',
      retryable: false,
      request_id: 'wreq_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    },
    '20': {
      protocol_version: 1,
      code: 'ATTACHMENT_STALE',
      workspace_state_at_close: 'RUNNING',
    },
    '21': {
      protocol_version: 1,
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      generation: '5',
      state: 'RUNNING',
      reason_code: null,
      runtime_epoch: '18446744073709551615',
    },
    '23': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      state: 'RUNNING',
      output_cursor: '0',
      admission_fence:
        '8888888888888888888888888888888888888888888888888888888888888888',
    },
    '25': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      result: 'committed',
      reason_code: null,
    },
    '26': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      lease_number: '4',
      acknowledged_hop_sequence: '6',
      requested_columns: 80,
      requested_rows: 24,
      effective_columns: 80,
      effective_rows: 24,
      result: 'applied',
      reason_code: null,
    },
    '27': {
      protocol_version: 1,
      attachment_id: 'att_11111111111111111111111111111111',
      workspace_id: 'aws_22222222222222222222222222222222',
      project_id: 'prj_33333333333333333333333333333333',
      agent_type: 'codex',
      runtime_host_installation_id: 'wri_44444444444444444444444444444444',
      runtime_host_installation_revision: '18446744073709551615',
      auth_epoch: '2',
      api_authority_epoch: '3',
      lease_number: '4',
      generation: '5',
      binding_revision: '6',
      mode: 'writer',
      binding_digest:
        '5555555555555555555555555555555555555555555555555555555555555555',
      runtime_epoch: '18446744073709551615',
      acknowledged_hop_sequence: '6',
      result: 'detached',
      cleanup_state: 'ATTACH_PTY_CLOSED',
      reason_code: null,
    },
  },
}
const TRACE: readonly (readonly [Leg, F])[] = [
  ['browser-to-api', 1],
  ['browser-to-api', 3],
  ['api-to-runtime', 2],
  ['api-to-runtime', 3],
  ['runtime-to-api', 7],
  ['runtime-to-api', 4],
  ['api-to-browser', 4],
  ['browser-to-api', 5],
  ['api-to-runtime', 5],
  ['runtime-to-api', 6],
  ['api-to-browser', 6],
  ['api-to-runtime', 22],
  ['runtime-to-api', 23],
  ['api-to-runtime', 24],
  ['runtime-to-api', 25],
  ['api-to-browser', 8],
]
function opaque(kind: F, size = 1, sequence = 1n, cursor = 1n): Uint8Array {
  const header = encodeAwceHeader({
    crypto_envelope_version: 1,
    direction_id: kind === F.INPUT ? 1 : 2,
    flags: 0,
    crypto_sequence: sequence,
    stream_cursor: kind === F.INPUT ? 0n : cursor,
    context_id: new Uint8Array(16).fill(0x66),
    ciphertext_length: size + 16,
  })
  const raw = new Uint8Array(44 + size + 16)
  raw.set(header)
  raw.fill(120, 44)
  return raw
}
function record(kind: F, leg: Leg): Record<string, unknown> {
  return { ...FIXTURES[leg][kind] }
}
function payload(kind: F, leg: Leg): WireRecord | Uint8Array {
  return kind === F.INPUT || kind === F.OUTPUT
    ? opaque(kind)
    : record(kind, leg)
}
function encoded(kind: F, leg: Leg, seq: bigint): Uint8Array {
  return encodeWireFrame(kind, leg, payload(kind, leg), seq)
}
function rawJson(kind: F, text: string | Uint8Array, seq = 1n): Uint8Array {
  const bytes =
      typeof text === 'string' ? new TextEncoder().encode(text) : text,
    raw = new Uint8Array(24 + bytes.length),
    v = new DataView(raw.buffer)
  v.setUint32(0, 0x41425753)
  v.setUint8(4, 1)
  v.setUint8(5, kind)
  v.setUint32(8, bytes.length)
  v.setBigUint64(12, seq)
  raw.set(bytes, 24)
  return raw
}
function session(count = 16): [WireSession, object] {
  const token = {},
    s = new WireSession(A, EPOCH, { streamId: token, startedAt: 0n })
  for (const [leg, kind] of TRACE.slice(0, count))
    s.accept(leg, encoded(kind, leg, s.expectedSequence(leg)), {
      streamId: token,
      now: 1n,
    })
  return [s, token]
}
function observe(
  s: WireSession,
  token: object,
  leg: Leg,
  kind: F,
  data: WireRecord | Uint8Array = payload(kind, leg),
  now = 2n,
): Uint8Array {
  const raw = encodeWireFrame(kind, leg, data, s.expectedSequence(leg))
  s.accept(leg, raw, { streamId: token, now })
  return raw
}

describe('all 27 types and four direction-specific closed profiles', () => {
  for (const leg of Object.values(Leg))
    for (const kind of Object.values(F))
      it(`${leg}/${kind}`, () => {
        if (!PROFILES[leg].includes(kind)) {
          expect(() => validatePayload(kind, leg, {})).toThrow(WireError)
          return
        }
        const frame = decodeWireFrame(encoded(kind, leg, 1n), leg, {
          admission: A,
          runtimeEpoch: EPOCH,
        })
        expect(frame.frameType).toBe(kind)
        expect(frame.hopSequence).toBe(1n)
        expect(frame.jsonPayload).toEqual(
          kind === 9 || kind === 10 ? null : payload(kind, leg),
        )
        expect(JSON.stringify(frame)).not.toContain('wat_')
        expect(String(frame)).toContain('<redacted>')
      })
  for (const leg of Object.values(Leg))
    for (const kind of PROFILES[leg].filter((k) => k !== 9 && k !== 10))
      it(`exact keys/scalars ${leg}/${kind}`, () => {
        const data = record(kind, leg)
        for (const key of Object.keys(data)) {
          const missing = { ...data }
          delete missing[key]
          expect(() => validatePayload(kind, leg, missing)).toThrow(WireError)
          expect(() =>
            validatePayload(kind, leg, { ...data, [key]: [] }),
          ).toThrow(WireError)
        }
        for (const key of [
          'command',
          'context',
          'ticket_extra',
          'input_sequence',
        ])
          expect(() =>
            validatePayload(kind, leg, { ...data, [key]: 'forbidden' }),
          ).toThrow(WireError)
      })
})
it.each([
  0,
  1,
  true,
  1.1,
  '',
  '0',
  '01',
  '+1',
  '1 ',
  ' 1',
  '-1',
  '1e0',
  '18446744073709551616',
  '１',
])('rejects noncanonical uint64 %s', (value) => {
  expect(() =>
    validatePayload(F.DETACH, BA, {
      ...record(F.DETACH, BA),
      lease_number: value,
    }),
  ).toThrow(WireError)
})
it.each(Object.keys(A) as (keyof AdmissionTuple)[])(
  'checks independently bound admission %s',
  (key) => {
    const alternate: Record<string, string> = {
      agent_type: 'claude',
      binding_digest: 'e'.repeat(64),
      mode: 'viewer',
    }
    const data = {
      ...record(F.KEY_INIT, BA),
      [key]:
        alternate[key] ??
        A[key].slice(0, -1) + (A[key].at(-1) === '9' ? '8' : '9'),
    }
    expect(() =>
      validatePayload(F.KEY_INIT, BA, data, { admission: A }),
    ).toThrow(WireError)
  },
)
it('uses pure derived context, no mode or protocol_id alias on keys', () => {
  expect(record(F.KEY_CONFIRM, BA)).toMatchObject(C)
  expect(() =>
    validatePayload(F.KEY_INIT, BA, {
      ...record(F.KEY_INIT, BA),
      protocol_id: 'agentbox-waw/v1',
    }),
  ).toThrow(WireError)
  expect(() =>
    validatePayload(F.KEY_CONFIRM, BA, {
      ...record(F.KEY_CONFIRM, BA),
      mode: 'writer',
    }),
  ).toThrow(WireError)
})
it.each([
  [F.KEY_INIT, BA, 'noise_message_1', 43],
  [F.KEY_INIT, BA, 'browser_ephemeral_public_key', 43],
  [F.KEY_ATTEST, RA, 'noise_message_2', 171],
  [F.KEY_ATTEST, RA, 'runtime_ephemeral_public_key', 43],
  [F.KEY_CONFIRM, BA, 'ciphertext', 64],
  [F.KEY_CONFIRM_ACK, RA, 'ciphertext', 64],
] as const)(
  'validates opaque key encoding %s %s %s',
  (kind, leg, key, length) => {
    for (const value of [
      'A'.repeat(length - 1),
      'A'.repeat(length + 1),
      ...['=', '+', ' ', 'é'].map((x) => 'A'.repeat(length - 1) + x),
    ])
      expect(() =>
        validatePayload(kind, leg, { ...record(kind, leg), [key]: value }),
      ).toThrow(WireError)
    if (length !== 64)
      expect(() =>
        validatePayload(kind, leg, {
          ...record(kind, leg),
          [key]: 'A'.repeat(length - 1) + 'B',
        }),
      ).toThrow(WireError)
    if (kind === F.KEY_INIT)
      expect(
        validatePayload(kind, leg, {
          ...record(kind, leg),
          [key]: 'B'.repeat(42) + 'A',
        }),
      ).toBeDefined()
  },
)
it.each([
  '{"protocol_version":1,"protocol_version":1}',
  '{"protocol_version":1,"x":{"same":1,"same":2}}',
  '{"protocol_version":1,"x":NaN}',
  '{"protocol_version":1,"x":Infinity}',
  '{"protocol_version":1,"x":1e999}',
  '{"protocol_version":1,"x":"\\ud800"}',
  '{"protocol_version":1,"\\udfff":1}',
  '{"protocol_version":1}true',
  '{"protocol_version":1}\u0000',
  '['.repeat(17) + ']'.repeat(17),
  '{' + Array.from({ length: 65 }, (_, i) => `"k${i}":0`).join(',') + '}',
  ' '.repeat(4097),
  '\ufeff{}',
])('rejects invalid/bounded strict JSON %#', (text) =>
  expect(() =>
    decodeWireFrame(rawJson(F.ERROR, text), AB, { trustedContext: false }),
  ).toThrow(WireError),
)
it('rejects invalid UTF8 and bad outer headers/trailing frames', () => {
  expect(() =>
    decodeWireFrame(rawJson(F.ERROR, new Uint8Array([255])), AB, {
      trustedContext: false,
    }),
  ).toThrow(WireError)
  const good = encoded(F.KEY_INIT, BA, 2n)
  for (const raw of [
    new Uint8Array(),
    good.slice(0, -1),
    new Uint8Array([...good, 0]),
    new Uint8Array([...good, ...good]),
  ])
    expect(() => decodeWireFrame(raw, BA)).toThrow(WireError)
  for (const offset of [0, 4, 5, 6, 7, 8, 20, 23]) {
    const bad = new Uint8Array(good)
    bad[offset] ^= 255
    expect(() => decodeWireFrame(bad, BA)).toThrow(WireError)
  }
})
for (const key of ['protocol_version', 'crypto_envelope_version'])
  it.each(['true', '"1"', '1.0', '1e0'])(
    `enforces literal ${key} %s`,
    (token) => {
      const text = JSON.stringify(record(F.KEY_INIT, BA)).replace(
        `"${key}":1`,
        `"${key}":${token}`,
      )
      expect(() => decodeWireFrame(rawJson(F.KEY_INIT, text), BA)).toThrow(
        WireError,
      )
    },
  )
it('accepts exactly integral Number spellings without rounding nonintegers', () => {
  const text = JSON.stringify(record(F.RESIZE, BA)).replace(
    '"columns":80',
    '"columns":8.0e1',
  )
  expect(decodeWireFrame(rawJson(F.RESIZE, text), BA).jsonPayload).toEqual(
    record(F.RESIZE, BA),
  )
  for (const token of [
    '8.00000000000000000000000000001e1',
    '80.0000000000000001',
    '240.00000000000000000001',
    '1e-999',
  ])
    expect(() =>
      decodeWireFrame(rawJson(F.RESIZE, text.replace('8.0e1', token)), BA),
    ).toThrow(WireError)
})
it('retains original key bytes and owns defensive copies', () => {
  const text = ' \n' + JSON.stringify(record(F.KEY_INIT, BA), null, 1) + '\t',
    raw = rawJson(F.KEY_INIT, text, 2n)
  const frame = decodeWireFrame(raw, BA),
    forwarded = forwardWireFrame(frame, AR, 7n)
  expect(Array.from(forwarded.slice(24))).toEqual(
    Array.from(new TextEncoder().encode(text)),
  )
  expect(forwarded.slice(0, 12)).toEqual(raw.slice(0, 12))
  expect(forwarded.slice(20)).toEqual(raw.slice(20))
  raw.fill(0)
  const copy = frame.payload
  copy.fill(0)
  expect(Array.from(frame.payload)).toEqual(
    Array.from(new TextEncoder().encode(text)),
  )
  expect(frame.wireBytes[0]).toBe(65)
  expect(Object.isFrozen(frame.jsonPayload)).toBe(true)
  expect(JSON.stringify(frame)).not.toContain('noise_message_1')
  let called = false
  const data = { ...record(F.KEY_INIT, BA) }
  Object.defineProperty(data, 'noise_message_1', {
    enumerable: true,
    get() {
      called = true
      return 'A'.repeat(43)
    },
  })
  expect(() => validatePayload(F.KEY_INIT, BA, data)).toThrow(WireError)
  expect(called).toBe(false)
})
it.each([
  [F.INPUT, BA, INPUT_LIMIT],
  [F.INPUT, AR, INPUT_LIMIT],
  [F.OUTPUT, RA, OUTPUT_LIMIT],
  [F.OUTPUT, AB, OUTPUT_LIMIT],
] as const)('applies effective envelope limits %s %s', (kind, leg, limit) => {
  for (const size of [1, limit])
    expect(encodeWireFrame(kind, leg, opaque(kind, size), 1n).length).toBe(
      24 + 44 + size + 16,
    )
  expect(() => validatePayload(kind, leg, opaque(kind, limit + 1))).toThrow(
    WireError,
  )
  expect(() =>
    validatePayload(kind, leg, opaque(kind === 9 ? F.OUTPUT : F.INPUT)),
  ).toThrow(WireError)
  for (const offset of [0, 4, 5, 6, 7, 24]) {
    const bad = opaque(kind)
    bad[offset] ^= 255
    expect(() => validatePayload(kind, leg, bad)).toThrow(WireError)
  }
  for (const offset of [8, 16]) {
    const bad = opaque(kind)
    new DataView(bad.buffer).setBigUint64(offset, 0xffffffffffffffffn)
    expect(() => validatePayload(kind, leg, bad)).toThrow(WireError)
  }
})
it('applies all conditional result schemas and direction-specific fields', () => {
  const positive: readonly (readonly [F, Leg, WireRecord])[] = [
    [
      F.RESIZE_ACK,
      RA,
      {
        result: 'rejected',
        reason_code: 'RESIZE_FAILED',
        effective_columns: null,
        effective_rows: null,
      },
    ],
    [
      F.DETACH_ACK,
      RA,
      {
        result: 'rejected',
        cleanup_state: 'ATTACH_PTY_CLOSE_UNCERTAIN',
        reason_code: 'DETACH_FAILED',
      },
    ],
    [F.DETACH_ACK, AB, { result: 'already_detached' }],
    [
      F.ADMISSION_COMMIT_ACK,
      RA,
      { result: 'rejected', reason_code: 'RECONCILIATION_REQUIRED' },
    ],
    [F.ACK, RA, { result: 'written_to_pty' }],
    [
      F.ACK,
      AB,
      { result: 'write_uncertain', reason_code: 'INPUT_WRITE_UNCERTAIN' },
    ],
    [F.ACK, RA, { result: 'rejected', reason_code: 'INPUT_RATE_LIMITED' }],
    [
      F.GAP,
      AB,
      { reason: 'baseline_redraw', from_cursor: '0', to_cursor: '0' },
    ],
  ]
  for (const [kind, leg, patch] of positive)
    expect(
      validatePayload(kind, leg, { ...record(kind, leg), ...patch }),
    ).toBeDefined()
  const negative: readonly (readonly [F, Leg, WireRecord])[] = [
    [F.RESIZE_ACK, RA, { effective_columns: 79 }],
    [F.RESIZE_ACK, AB, { result: 'rejected' }],
    [F.DETACH_ACK, RA, { cleanup_state: 'ATTACH_PTY_CLOSE_UNCERTAIN' }],
    [
      F.DETACH_ACK,
      AB,
      { result: 'rejected', reason_code: 'DETACH_IN_PROGRESS' },
    ],
    [F.ADMISSION_COMMIT_ACK, RA, { result: 'rejected' }],
    [
      F.ADMISSION_COMMIT_ACK,
      RA,
      { result: 'rejected', reason_code: 'INTERNAL_BOUNDED' },
    ],
    [F.ACK, RA, { result: 'write_uncertain' }],
    [F.ACK, RA, { reason_code: 'INPUT_RATE_LIMITED' }],
    [F.ACK, RA, { result: 'rejected', reason_code: 'INPUT_WRITE_UNCERTAIN' }],
    [F.ACK, RA, { browser_input_hop_sequence: '4' }],
    [F.GAP, AB, { reason: 'baseline_redraw' }],
    [F.GAP, RA, { from_cursor: '0' }],
    [F.GAP, RA, { from_cursor: '18446744073709551615' }],
    [F.GAP, RA, { to_cursor: '1' }],
    [F.STATE, AB, { runtime_epoch: EPOCH }],
    [F.CLOSE, RA, { code: 'INTERNAL_BOUNDED' }],
    [F.CLOSE, AB, { code: 'INTERNAL_BOUNDED' }],
    [F.CLOSE, AR, { code: 'WORKSPACE_EXITED' }],
    [F.ERROR, AB, { code: 'new_error' }],
    [F.ERROR, AB, { request_id: null }],
    [F.ADMITTED, AB, { lease_expires_at: '2030-02-29T00:00:00.123456Z' }],
    [F.ADMITTED, AB, { lease_expires_at: '2030-03-01T00:00:00.123Z' }],
  ]
  for (const [kind, leg, patch] of negative)
    expect(() =>
      validatePayload(kind, leg, { ...record(kind, leg), ...patch }),
    ).toThrow(WireError)
  expect(
    validatePayload(F.CLOSE, AR, {
      ...record(F.CLOSE, AR),
      code: 'INTERNAL_BOUNDED',
    }),
  ).toBeDefined()
})
it('accepts exact normal trace and independently contiguous hops/crypto', () => {
  const [s, token] = session()
  expect(s.admitted).toBe(true)
  expect(s.committed).toBe(true)
  expect(Object.values(Leg).map((leg) => s.expectedSequence(leg))).toEqual([
    4n,
    4n,
    6n,
    6n,
  ])
  for (const [leg, kind] of [
    [BA, F.INPUT],
    [AR, F.INPUT],
    [RA, F.OUTPUT],
    [AB, F.OUTPUT],
  ] as const)
    observe(s, token, leg, kind)
  for (const leg of [BA, AR, RA]) observe(s, token, leg, F.HEARTBEAT)
  observe(s, token, BA, F.INPUT, opaque(F.INPUT, 1, 2n))
  observe(s, token, AR, F.INPUT, opaque(F.INPUT, 1, 2n))
})
it.each(TRACE.map((_, i) => i))(
  'forbids active frame before ADMITTED at stage %s',
  (count) => {
    const [s, token] = session(count),
      expected = s.expectedSequence(BA)
    expect(() => observe(s, token, BA, F.INPUT)).toThrow(WireError)
    expect(s.closed).toBe(true)
    expect(s.expectedSequence(BA)).toBe(expected)
  },
)
it('accepts one exact commit/ACK replay without advancing hops', () => {
  const [s, token] = session(15),
    commit = encoded(F.ADMISSION_COMMIT, AR, 5n),
    ack = encoded(F.ADMISSION_COMMIT_ACK, RA, 5n)
  expect(s.accept(AR, commit, { streamId: token, now: 2n }).replay).toBe(true)
  expect(s.accept(RA, ack, { streamId: token, now: 3n }).replay).toBe(true)
  expect(s.expectedSequence(AR)).toBe(6n)
  expect(s.expectedSequence(RA)).toBe(6n)
  observe(s, token, AB, F.ADMITTED, record(F.ADMITTED, AB), 4n)
  expect(() => s.accept(AR, commit, { streamId: token, now: 5n })).toThrow(
    WireError,
  )
})
it.each(['second', 'altered', 'stream', 'late', 'early_ack', 'after_terminal'])(
  'rejects commit replay %s',
  (variation) => {
    const [s, original] = session(15)
    let token = original,
      raw = encoded(F.ADMISSION_COMMIT, AR, 5n),
      now = 2n,
      leg: Leg = AR
    if (variation === 'second') s.accept(AR, raw, { streamId: token, now })
    if (variation === 'altered')
      raw = rawJson(
        F.ADMISSION_COMMIT,
        JSON.stringify(record(F.ADMISSION_COMMIT, AR), null, 1),
        5n,
      )
    if (variation === 'stream') token = {}
    if (variation === 'late') now = 5_000_000_000n
    if (variation === 'after_terminal') observe(s, token, RA, F.ERROR)
    if (variation === 'early_ack') {
      raw = encoded(F.ADMISSION_COMMIT_ACK, RA, 5n)
      leg = RA
    }
    expect(() => s.accept(leg, raw, { streamId: token, now })).toThrow(
      WireError,
    )
    expect(s.closed).toBe(true)
  },
)
it('rejects reserialized relay and altered baseline/fence', () => {
  const [s, token] = session(3)
  expect(() =>
    s.accept(
      AR,
      rawJson(F.KEY_INIT, JSON.stringify(record(F.KEY_INIT, AR), null, 1), 2n),
      { streamId: token, now: 2n },
    ),
  ).toThrow(WireError)
  for (const [count, leg, kind, key, value] of [
    [12, RA, F.STREAM_READY_ACK, 'output_cursor', '1'],
    [13, AR, F.ADMISSION_COMMIT, 'admission_fence', 'f'.repeat(64)],
    [15, AB, F.ADMITTED, 'runtime_epoch', '1'],
  ] as const) {
    const [trace, id] = session(count)
    expect(() =>
      observe(trace, id, leg, kind, { ...record(kind, leg), [key]: value }),
    ).toThrow(WireError)
  }
})
it('accepts only exact early and trusted failure order', () => {
  const token = {},
    s = new WireSession(A, EPOCH, { streamId: token, startedAt: 0n })
  s.accept(
    AB,
    encodeWireFrame(
      F.ERROR,
      AB,
      { ...record(F.ERROR, AB), request_id: null },
      1n,
      { trustedContext: false },
    ),
    { streamId: token, now: 1n },
  )
  expect(() => observe(s, token, AB, F.CLOSE)).toThrow(WireError)
  for (const count of [4, 5]) {
    const [trace, id] = session(count)
    observe(trace, id, RA, F.ERROR)
    expect(() => observe(trace, id, RA, F.CLOSE)).toThrow(WireError)
  }
  for (const count of [6, 12, 14]) {
    const [trace, id] = session(count)
    observe(trace, id, RA, F.STATE, {
      ...record(F.STATE, RA),
      state: 'UNKNOWN',
      reason_code: 'RECONCILIATION_REQUIRED',
    })
    observe(trace, id, RA, F.CLOSE)
    observe(trace, id, AB, F.ERROR)
    if (count === 6)
      expect(() => observe(trace, id, AB, F.CLOSE)).toThrow(WireError)
    else observe(trace, id, AB, F.CLOSE)
    expect(trace.admitted).toBe(false)
  }
})
it('translates terminal EXIT and closes before further output', () => {
  const [s, token] = session()
  observe(s, token, RA, F.EXIT)
  observe(s, token, RA, F.CLOSE)
  observe(s, token, AB, F.EXIT)
  observe(s, token, AB, F.CLOSE)
  expect(() => observe(s, token, RA, F.OUTPUT)).toThrow(WireError)
})
it('accepts one internal DETACH retry and exact terminal mapping', () => {
  const [s, token] = session()
  observe(s, token, BA, F.DETACH)
  const raw = observe(s, token, AR, F.DETACH)
  expect(s.accept(AR, raw, { streamId: token, now: 3n }).replay).toBe(true)
  observe(s, token, RA, F.DETACH_ACK, record(F.DETACH_ACK, RA), 4n)
  observe(
    s,
    token,
    AB,
    F.DETACH_ACK,
    { ...record(F.DETACH_ACK, AB), acknowledged_hop_sequence: '4' },
    4n,
  )
  observe(s, token, RA, F.CLOSE, record(F.CLOSE, RA), 4n)
  observe(s, token, AB, F.CLOSE, record(F.CLOSE, AB), 4n)
  expect(s.admitted).toBe(false)
})
it.each(['browser', 'second', 'after_ack', 'late', 'changed'])(
  'rejects DETACH retry %s',
  (variation) => {
    const [s, token] = session(),
      browser = observe(s, token, BA, F.DETACH)
    let raw = observe(s, token, AR, F.DETACH),
      leg: Leg = AR,
      now = 3n
    if (variation === 'browser') {
      raw = browser
      leg = BA
    }
    if (variation === 'second') s.accept(AR, raw, { streamId: token, now })
    if (variation === 'after_ack') observe(s, token, RA, F.DETACH_ACK)
    if (variation === 'late') now = 5_000_000_002n
    if (variation === 'changed')
      raw = rawJson(F.DETACH, JSON.stringify(record(F.DETACH, AR), null, 1), 6n)
    expect(() => s.accept(leg, raw, { streamId: token, now })).toThrow(
      WireError,
    )
  },
)
it('checks a bounded validation deadline and fails without hop allocation', () => {
  const raw = encoded(F.KEY_INIT, BA, 2n),
    timer = vi
      .spyOn(performance, 'now')
      .mockReturnValueOnce(0)
      .mockReturnValueOnce(6)
  expect(() => decodeWireFrame(raw, BA)).toThrow(WireError)
  timer.mockRestore()
  for (const seq of [0n, 2n, 0xffffffffffffffffn]) {
    const [s, token] = session(0)
    expect(() =>
      s.accept(
        BA,
        rawJson(F.WS_HELLO, JSON.stringify(record(F.WS_HELLO, BA)), seq),
        { streamId: token, now: 1n },
      ),
    ).toThrow(WireError)
    expect(s.expectedSequence(BA)).toBe(1n)
    expect(s.closed).toBe(true)
  }
})
it('checks explicit Number dimension, timestamp and exit bounds', () => {
  for (const [field, valid, invalid] of [
    ['columns', [8, 240], [0, 7, 241, true, 8.5, '80', null]],
    ['rows', [1, 200], [0, 201, false, 1.1, '24', null]],
  ] as const) {
    for (const value of valid)
      expect(
        validatePayload(F.RESIZE, BA, {
          ...record(F.RESIZE, BA),
          [field]: value,
        }),
      ).toBeDefined()
    for (const value of invalid)
      expect(() =>
        validatePayload(F.RESIZE, BA, {
          ...record(F.RESIZE, BA),
          [field]: value,
        }),
      ).toThrow(WireError)
  }
  for (const value of [-128, 255, null])
    expect(
      validatePayload(F.EXIT, RA, { ...record(F.EXIT, RA), exit_code: value }),
    ).toBeDefined()
  for (const value of [-129, 256, false, 1.5, '1'])
    expect(() =>
      validatePayload(F.EXIT, RA, { ...record(F.EXIT, RA), exit_code: value }),
    ).toThrow(WireError)
  for (const value of [
    '2000-02-29T23:59:59.999999Z',
    '0001-01-01T00:00:00.000000Z',
  ])
    expect(
      validatePayload(F.ADMITTED, AB, {
        ...record(F.ADMITTED, AB),
        lease_expires_at: value,
      }),
    ).toBeDefined()
  for (const value of [
    '1900-02-29T00:00:00.000000Z',
    '0000-01-01T00:00:00.000000Z',
    '2030-01-01T00:00:60.000000Z',
    '2030-01-01T24:00:00.000000Z',
  ])
    expect(() =>
      validatePayload(F.ADMITTED, AB, {
        ...record(F.ADMITTED, AB),
        lease_expires_at: value,
      }),
    ).toThrow(WireError)
})
it('handles extreme exponents with a bounded failure and closes the trace', () => {
  for (const token of ['1e' + '9'.repeat(1000), '1e-' + '9'.repeat(1000)]) {
    const text = JSON.stringify(record(F.RESIZE, BA)).replace(
        '"columns":80',
        '"columns":' + token,
      ),
      [s, id] = session()
    expect(() =>
      s.accept(BA, rawJson(F.RESIZE, text, 4n), { streamId: id, now: 2n }),
    ).toThrow(WireError)
    expect(s.closed).toBe(true)
    expect(s.expectedSequence(BA)).toBe(4n)
  }
})
it('allows committed quarantined OUTPUT but no internal INPUT before ADMITTED', () => {
  const [s, id] = session(15)
  observe(s, id, RA, F.OUTPUT)
  expect(s.admitted).toBe(false)
  expect(() => observe(s, id, AR, F.INPUT)).toThrow(WireError)
})
it.each(['crypto_skip', 'crypto_replay', 'context', 'cursor_regression'])(
  'fences active envelope %s',
  (variation) => {
    const [s, id] = session(),
      leg = variation === 'cursor_regression' ? RA : BA,
      kind = variation === 'cursor_regression' ? F.OUTPUT : F.INPUT
    if (['crypto_replay', 'cursor_regression'].includes(variation))
      observe(s, id, leg, kind)
    const raw = opaque(
      kind,
      1,
      ['crypto_skip', 'cursor_regression'].includes(variation) ? 2n : 1n,
    )
    if (variation === 'context') raw[28] = 122
    expect(() => observe(s, id, leg, kind, raw)).toThrow(WireError)
    expect(s.closed).toBe(true)
  },
)
it.each([
  [RA, 6],
  [RA, 12],
  [RA, 14],
  [AB, 7],
  [AB, 15],
] as const)(
  'never accepts RUNNING STATE as admission success %s %s',
  (leg, count) => {
    const [s, id] = session(count)
    expect(() => observe(s, id, leg, F.STATE)).toThrow(WireError)
    expect(s.closed).toBe(true)
  },
)
it('keeps browser WAIT_KEY_ATTEST on ERROR plus native close only', () => {
  const [s, id] = session(6)
  expect(() =>
    observe(s, id, AB, F.STATE, { ...record(F.STATE, AB), state: 'UNKNOWN' }),
  ).toThrow(WireError)
  const [second, identity] = session(6)
  observe(second, identity, AB, F.ERROR)
  expect(() => observe(second, identity, AB, F.CLOSE)).toThrow(WireError)
})
it('cannot reopen a terminal trace with RUNNING STATE', () => {
  const [s, id] = session()
  observe(s, id, RA, F.EXIT)
  expect(() => observe(s, id, AB, F.STATE)).toThrow(WireError)
})
it('accepts ACTIVE NEEDS_INTERACTION metadata without implying close', () => {
  const [s, id] = session()
  for (const leg of [RA, AB])
    observe(s, id, leg, F.STATE, {
      ...record(F.STATE, leg),
      state: 'NEEDS_INTERACTION',
    })
  expect(s.failed).toBe(false)
  expect(s.admitted).toBe(true)
  observe(s, id, BA, F.HEARTBEAT)
})
it.each([
  [F.INPUT, BA, AR],
  [F.OUTPUT, RA, AB],
] as const)(
  'requires original FIFO source for immutable relay %s',
  (kind, source, target) => {
    const [s, id] = session()
    expect(() => observe(s, id, target, kind)).toThrow(WireError)
    const [changed, identity] = session(),
      original = opaque(kind)
    observe(changed, identity, source, kind, original)
    const altered = new Uint8Array(original)
    altered[altered.length - 1] = 33
    expect(() => observe(changed, identity, target, kind, altered)).toThrow(
      WireError,
    )
    const [outOfOrder, key] = session()
    for (const sequence of [1n, 2n])
      observe(
        outOfOrder,
        key,
        source,
        kind,
        opaque(kind, 1, sequence, sequence),
      )
    expect(() =>
      observe(outOfOrder, key, target, kind, opaque(kind, 1, 2n, 2n)),
    ).toThrow(WireError)
  },
)
it.each([
  [F.INPUT, BA],
  [F.OUTPUT, RA],
] as const)('bounds pending relay record count %s', (kind, source) => {
  const [s, id] = session()
  for (let seq = 1n; seq <= 256n; seq++)
    observe(s, id, source, kind, opaque(kind, 1, seq, seq))
  const expected = s.expectedSequence(source)
  expect(() =>
    observe(s, id, source, kind, opaque(kind, 1, 257n, 257n)),
  ).toThrow(WireError)
  expect(s.closed).toBe(true)
  expect(s.expectedSequence(source)).toBe(expected)
})
it.each([
  [16, F.INPUT, BA, INPUT_LIMIT, 3],
  [15, F.OUTPUT, RA, OUTPUT_LIMIT, 1],
  [16, F.OUTPUT, RA, OUTPUT_LIMIT, 7],
] as const)(
  'bounds complete pending encoded frames %s %s',
  (count, kind, leg, size, accepted) => {
    const [s, id] = session(count)
    for (let seq = 1n; seq <= BigInt(accepted); seq++)
      observe(s, id, leg, kind, opaque(kind, size, seq, seq))
    expect(() =>
      observe(
        s,
        id,
        leg,
        kind,
        opaque(kind, size, BigInt(accepted + 1), BigInt(accepted + 1)),
      ),
    ).toThrow(WireError)
    expect(s.closed).toBe(true)
  },
)
it('releases bounded records only after the exact relay', () => {
  const [s, id] = session()
  for (let seq = 1n; seq < 300n; seq++) {
    const data = opaque(F.INPUT, 1, seq)
    observe(s, id, BA, F.INPUT, data)
    observe(s, id, AR, F.INPUT, data)
  }
  expect(s.closed).toBe(false)
})

it('only keeps admitted API browser retryable control-limit errors nonfatal', () => {
  for (const leg of Object.values(Leg)) {
    for (const admitted of [false, true]) {
      for (const retryable of [false, true]) {
        const [trace, id] = session(admitted ? 16 : 15)
        const data = {
          protocol_version: 1,
          code: 'CONTROL_RATE_LIMITED',
          retryable,
          request_id: 'wreq_' + 'a'.repeat(32),
        }
        if (leg === BA || leg === AR) {
          expect(() => observe(trace, id, leg, F.ERROR, data)).toThrow(
            WireError,
          )
          continue
        }
        observe(trace, id, leg, F.ERROR, data)
        if (admitted && leg === AB && retryable) {
          observe(trace, id, BA, F.INPUT)
          observe(trace, id, AR, F.INPUT)
        } else {
          expect(() => observe(trace, id, BA, F.INPUT)).toThrow(WireError)
        }
      }
    }
  }
  const [trace, id] = session()
  observe(trace, id, AB, F.ERROR, {
    ...record(F.ERROR, AB),
    code: 'INPUT_RATE_LIMITED',
    retryable: true,
  })
  expect(() => observe(trace, id, BA, F.INPUT)).toThrow(WireError)
})
