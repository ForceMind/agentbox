import { describe, expect, it } from 'vitest'

import {
  WAWRc7BrowserSocket,
  WAWRc7Checkpoints,
  WAWRc7DeferredCrypto,
  WAWRc7DeferredRenderer,
  WAWRc7FakeClock,
  createWAWRc7Gate,
  createWAWRc7Schedule,
  type WAWRc7CryptoDelegate,
} from './wawRc7TestHarness'

describe('WAW rc7 test harness', () => {
  it('only accepts closed named checkpoints and rejects duplicate arrival', async () => {
    const checkpoints = new WAWRc7Checkpoints(['ticket-issued'])
    const pending = checkpoints.arrive('ticket-issued')
    await expect(checkpoints.reached('ticket-issued')).resolves.toBeUndefined()
    expect(() => checkpoints.arrive('ticket-issued')).toThrow(
      'after declared sequence',
    )
    // The union is compile-time closed; runtime input is also rejected.
    expect(() => checkpoints.arrive('unknown' as never)).toThrow('unknown')
    checkpoints.release('ticket-issued')
    await expect(pending).resolves.toBeUndefined()
  })

  it('counts repeated declared checkpoints without admitting an extra arrival', async () => {
    const checkpoints = new WAWRc7Checkpoints([
      'heartbeat-send',
      'heartbeat-send',
    ])
    const first = checkpoints.arrive('heartbeat-send')
    await expect(checkpoints.reached('heartbeat-send')).resolves.toBeUndefined()
    checkpoints.release('heartbeat-send')
    await expect(first).resolves.toBeUndefined()

    const second = checkpoints.arrive('heartbeat-send')
    await expect(
      checkpoints.reached('heartbeat-send', 2),
    ).resolves.toBeUndefined()
    checkpoints.release('heartbeat-send', 2)
    await expect(second).resolves.toBeUndefined()
    checkpoints.assertComplete()
    expect(() => checkpoints.arrive('heartbeat-send')).toThrow(
      'after declared sequence',
    )
  })

  it('rejects unknown plans and requires every arrived gate to depart', async () => {
    expect(() => new WAWRc7Checkpoints(['unknown' as never])).toThrow('unknown')
    const checkpoints = new WAWRc7Checkpoints(['admitted'])
    expect(() => checkpoints.release('admitted')).toThrow('has not arrived')
    const pending = checkpoints.arrive('admitted')
    await expect(checkpoints.reached('admitted')).resolves.toBeUndefined()
    expect(() => checkpoints.assertComplete()).toThrow('incomplete')
    checkpoints.fail('admitted')
    await expect(pending).rejects.toThrow('rc7 deferred rejected')
    checkpoints.assertComplete()
  })

  it('rejects late checkpoint release and duplicate deferred settlement', () => {
    const checkpoints = new WAWRc7Checkpoints(['admitted'])
    expect(() => checkpoints.release('admitted')).toThrow('has not arrived')
    const deferred = createWAWRc7Gate()
    deferred.resolve()
    expect(() => deferred.resolve()).toThrow('already settled')
  })

  it('reaches key confirmation only after the real crypto delegate verifies it', async () => {
    const checkpoints = new WAWRc7Checkpoints(['key-confirm'])
    const calls: string[] = []
    const delegate: WAWRc7CryptoDelegate = {
      state: 'WAIT_ACK',
      destroy: () => undefined,
      writeKeyInit: async () => {
        throw new Error('not used')
      },
      readKeyAttest: async () => {
        throw new Error('not used')
      },
      readKeyConfirmAck: async () => {
        calls.push('verified')
      },
      encryptInput: async () => {
        throw new Error('not used')
      },
      decryptOutput: async () => {
        throw new Error('not used')
      },
    }
    const crypto = new WAWRc7DeferredCrypto(delegate, checkpoints)
    const pending = crypto.readKeyConfirmAck({})
    await expect(checkpoints.reached('key-confirm')).resolves.toBeUndefined()
    expect(calls).toEqual(['verified'])
    checkpoints.release('key-confirm')
    await expect(pending).resolves.toBeUndefined()
    checkpoints.assertComplete()
  })

  it('hands render work to the real delegate before holding its checkpoint', async () => {
    const checkpoints = new WAWRc7Checkpoints(['output-render'])
    let calls = 0
    let capturedLength = 0
    let resolveRender!: () => void
    const renderPending = new Promise<void>((resolve) => {
      resolveRender = resolve
    })
    const renderer = new WAWRc7DeferredRenderer(
      {
        enqueueFrame: async (bytes) => {
          calls += 1
          capturedLength = bytes.byteLength
          await renderPending
        },
        resize: () => undefined,
        cancelAttachment: () => undefined,
      },
      checkpoints,
    )
    const pending = renderer.enqueueFrame(new Uint8Array(3))
    await expect(checkpoints.reached('output-render')).resolves.toBeUndefined()
    expect({ calls, capturedLength }).toEqual({ calls: 1, capturedLength: 3 })
    checkpoints.release('output-render')
    resolveRender()
    await expect(pending).resolves.toBeUndefined()
    checkpoints.assertComplete()
  })

  it('uses a monotonic clock and only runs due scheduled work', () => {
    const clock = new WAWRc7FakeClock(10)
    const scheduled = createWAWRc7Schedule(clock)
    let calls = 0
    scheduled.schedule(() => {
      calls += 1
    }, 5)
    scheduled.runDue()
    expect(calls).toBe(0)
    clock.advanceBy(5)
    scheduled.runDue()
    expect(calls).toBe(1)
    scheduled.assertDrained()
    expect(() => clock.advanceTo(14)).toThrow('cannot move backwards')
    expect(() => clock.advanceBy(-1)).toThrow('cannot move backwards')
  })

  it('scripts partial socket state, events, buffering and send failure', () => {
    const socket = new WAWRc7BrowserSocket()
    const events: string[] = []
    socket.subscribe({
      open: () => events.push('open'),
      message: () => events.push('message'),
      error: () => events.push('error'),
      close: () => events.push('close'),
    })
    socket.open('agentbox-waw-v1')
    socket.setBufferedAmount(7)
    socket.send(new Uint8Array([1, 2]))
    socket.message(new Uint8Array([3]).buffer)
    socket.error()
    expect(socket.sentMetadata).toHaveLength(1)
    expect(socket.takeSentBytes()).toEqual([new Uint8Array([1, 2])])
    expect(socket.takeSentBytes()).toEqual([])
    socket.remoteClose()
    expect({
      state: socket.state,
      readyState: socket.readyState,
      protocol: socket.protocol,
      bufferedAmount: socket.bufferedAmount,
      events,
    }).toEqual({
      state: 'closed',
      readyState: 3,
      protocol: '',
      bufferedAmount: 0,
      events: ['open', 'message', 'error', 'close'],
    })
    const failed = new WAWRc7BrowserSocket()
    failed.open('agentbox-waw-v1')
    failed.failSends(new Error('injected send failure'))
    expect(() => failed.send(new Uint8Array([1]))).toThrow(
      'rc7 injected send failure',
    )
    failed.close()
    socket.assertDrained()
    failed.assertDrained()
  })

  it('does not expose checkpoint state through enumerable diagnostic fields', () => {
    const checkpoints = new WAWRc7Checkpoints(['ticket-issued'])
    const socket = new WAWRc7BrowserSocket()
    expect(JSON.stringify(checkpoints)).toBe('{}')
    expect(JSON.stringify(socket)).toBe('{"binaryType":"arraybuffer"}')
  })
})
