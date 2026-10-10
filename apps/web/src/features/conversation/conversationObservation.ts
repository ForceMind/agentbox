/**
 * Inert K2 metadata projection. No production adapter imports this module.
 * Inputs are decoded synthetic metadata, not authenticated wire messages.
 * Tuple matching never grants execution, content, approval or write authority.
 */
import { isCanonicalUint64 } from '../workspace/workspaceState'
import { isProjectId } from '../workspace/workspaceMetadata'

const scopeKeys = [
  'owner_scope',
  'auth_epoch',
  'project_id',
  'project_revision',
  'binding_revision',
  'binding_digest',
  'host_id',
  'host_revision',
  'runtime_epoch',
  'api_authority_epoch',
  'agent_type',
  'execution_kind',
  'conversation_id',
  'conversation_revision',
  'generation',
  'turn_id',
] as const
const numericKeys = [
  'auth_epoch',
  'project_revision',
  'binding_revision',
  'host_revision',
  'runtime_epoch',
  'api_authority_epoch',
  'conversation_revision',
  'generation',
] as const
const statuses = [
  'running',
  'awaiting_approval',
  'awaiting_input',
  'completed',
  'failed',
  'canceled',
  'unknown',
] as const

type ScopeKey = (typeof scopeKeys)[number]
export type ConversationScope = Readonly<
  Record<ScopeKey, string> & {
    agent_type: 'claude' | 'codex'
    execution_kind: 'structured-candidate'
  }
>
export type ConversationObservation = Readonly<{
  scope: ConversationScope
  revision: string
  status: (typeof statuses)[number]
}>
export type ConversationObservationState = Readonly<{
  viewId: string
  scope: ConversationScope
  observation: ConversationObservation | null
  freshness: 'unobserved' | 'fresh' | 'stale' | 'incomplete' | 'conflict'
  readFloor: string
  revisionFloor: string
  pendingRead: string | null
}>

function invalid(): never {
  throw new Error('Invalid conversation observation')
}
function object(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalid()
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) invalid()
  const names = Reflect.ownKeys(value)
  if (
    names.length !== keys.length ||
    names.some((key) => typeof key !== 'string' || !keys.includes(key))
  )
    invalid()
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key)
    if (!descriptor || !descriptor.enumerable || !('value' in descriptor))
      invalid()
  }
  return value as Record<string, unknown>
}
function decimal(value: unknown): value is string {
  // The existing helper supplies bounded uint64 arithmetic; the explicit trim
  // check also rejects a final newline before JavaScript's `$` regex anchor.
  return isCanonicalUint64(value, true) && value.trim() === value
}
function hex(value: unknown, length: number): value is string {
  return (
    typeof value === 'string' &&
    value.length === length &&
    /^[a-f0-9]+$/.test(value)
  )
}
function id(value: unknown, prefix: string): value is string {
  return (
    typeof value === 'string' &&
    value.length === prefix.length + 32 &&
    value.startsWith(prefix) &&
    hex(value.slice(prefix.length), 32)
  )
}
export function parseConversationScope(value: unknown): ConversationScope {
  const row = object(value, scopeKeys)
  if (
    !hex(row.owner_scope, 64) ||
    !hex(row.binding_digest, 64) ||
    !id(row.project_id, 'prj_') ||
    !isProjectId(row.project_id) ||
    !id(row.host_id, 'wri_') ||
    !id(row.conversation_id, 'kcv_') ||
    !id(row.turn_id, 'ktr_') ||
    (row.agent_type !== 'claude' && row.agent_type !== 'codex') ||
    row.execution_kind !== 'structured-candidate' ||
    numericKeys.some((key) => !decimal(row[key]))
  )
    invalid()
  return Object.freeze({ ...row }) as ConversationScope
}
export function parseConversationObservation(
  value: unknown,
): ConversationObservation {
  const row = object(value, ['scope', 'revision', 'status'])
  const scope = parseConversationScope(row.scope)
  if (
    !decimal(row.revision) ||
    typeof row.status !== 'string' ||
    !(statuses as readonly string[]).includes(row.status)
  )
    invalid()
  return Object.freeze({
    scope,
    revision: row.revision,
    status: row.status as ConversationObservation['status'],
  })
}
function sameScope(a: ConversationScope, b: ConversationScope): boolean {
  return scopeKeys.every((key) => a[key] === b[key])
}
function state(
  value: ConversationObservationState,
): ConversationObservationState {
  return Object.freeze(value)
}
export function createConversationObservationState(
  scope: unknown,
  viewId: unknown,
): ConversationObservationState {
  if (!hex(viewId, 32)) invalid()
  return state({
    viewId,
    scope: parseConversationScope(scope),
    observation: null,
    freshness: 'unobserved',
    readFloor: '0',
    revisionFloor: '0',
    pendingRead: null,
  })
}
export function beginConversationRead(
  current: ConversationObservationState,
  attempt: unknown,
): ConversationObservationState {
  if (!decimal(attempt)) invalid()
  if (
    current.freshness === 'conflict' ||
    BigInt(attempt) <= BigInt(current.readFloor)
  )
    return current
  return state({
    ...current,
    freshness: 'stale',
    readFloor: attempt,
    pendingRead: attempt,
  })
}
export function interruptConversationObservation(
  current: ConversationObservationState,
): ConversationObservationState {
  if (current.freshness === 'conflict') return current
  return state({ ...current, freshness: 'stale', pendingRead: null })
}
function conflicts(
  previous: ConversationObservation,
  next: ConversationObservation,
): boolean {
  return (
    previous.status !== next.status &&
    (previous.revision === next.revision ||
      ['completed', 'failed', 'canceled'].includes(previous.status))
  )
}
function conflict(
  current: ConversationObservationState,
): ConversationObservationState {
  return state({ ...current, freshness: 'conflict', pendingRead: null })
}
export function acceptConversationSnapshot(
  current: ConversationObservationState,
  viewId: unknown,
  attempt: unknown,
  value: unknown,
): ConversationObservationState {
  if (
    current.freshness === 'conflict' ||
    viewId !== current.viewId ||
    current.pendingRead === null ||
    attempt !== current.pendingRead
  )
    return current
  const next = parseConversationObservation(value)
  if (!sameScope(current.scope, next.scope)) return current
  if (BigInt(next.revision) < BigInt(current.revisionFloor)) return current
  const previous = current.observation
  if (previous) {
    if (BigInt(next.revision) < BigInt(previous.revision)) return current
    if (conflicts(previous, next)) return conflict(current)
  }
  return state({
    ...current,
    observation: next,
    revisionFloor: next.revision,
    freshness: 'fresh',
    pendingRead: null,
  })
}
export function acceptConversationEvent(
  current: ConversationObservationState,
  viewId: unknown,
  value: unknown,
): ConversationObservationState {
  const previous = current.observation
  if (
    current.freshness !== 'fresh' ||
    viewId !== current.viewId ||
    previous === null
  )
    return current
  const next = parseConversationObservation(value)
  if (!sameScope(current.scope, next.scope)) return current
  const before = BigInt(previous.revision)
  const after = BigInt(next.revision)
  if (after < before) return current
  if (conflicts(previous, next)) return conflict(current)
  if (after === before) return current
  if (after !== before + 1n)
    return state({
      ...current,
      freshness: 'incomplete',
      pendingRead: null,
      revisionFloor: next.revision,
    })
  return state({ ...current, observation: next, revisionFloor: next.revision })
}
