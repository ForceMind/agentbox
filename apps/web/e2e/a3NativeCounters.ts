/** Fixed numeric diagnostics only. Never retain or decode content/metadata bytes. */
const limit = 65_535
const initial = {
  sockets_created: 0,
  sockets_opened: 0,
  sockets_closed: 0,
  socket_errors: 0,
  ready_received: 0,
  current_received: 0,
  current_sent: 0,
  consumption_sent: 0,
  opaque_sent: 0,
  opaque_received: 0,
}
type Counter = keyof typeof initial

export class A3NativeCounters {
  private values = { ...initial }

  event(name: Counter) {
    this.values[name] = Math.min(limit, this.values[name] + 1)
  }

  frame(direction: 'sent' | 'received', payload: string | Buffer) {
    const control = (prefix: string, length: number) =>
      Buffer.isBuffer(payload) &&
      payload.length === length &&
      payload[4] === 1 &&
      payload[0] === prefix.charCodeAt(0) &&
      payload[1] === prefix.charCodeAt(1) &&
      payload[2] === prefix.charCodeAt(2) &&
      payload[3] === prefix.charCodeAt(3)
    if (direction === 'received') {
      this.event(
        control('A3RD', 5)
          ? 'ready_received'
          : control('A3CR', 25)
            ? 'current_received'
            : 'opaque_received',
      )
    } else {
      this.event(
        control('A3CQ', 25)
          ? 'current_sent'
          : control('A3CA', 41)
            ? 'consumption_sent'
            : 'opaque_sent',
      )
    }
  }

  snapshot() {
    return Object.freeze({ ...this.values })
  }
}

export function a3FixtureStatusNumbers(raw: unknown) {
  const value =
    raw !== null && typeof raw === 'object'
      ? (raw as Record<string, unknown>)
      : {}
  const count = (name: string) => {
    const item = value[name]
    return typeof item === 'number' &&
      Number.isSafeInteger(item) &&
      item >= 0 &&
      item <= 2_147_483_647
      ? item
      : -1
  }
  return {
    diff_count: count('diff_count'),
    held: typeof value.held === 'boolean' ? Number(value.held) : -1,
    active: count('active'),
    burned_nonces: count('burned_nonces'),
    connections: count('connections'),
  }
}
