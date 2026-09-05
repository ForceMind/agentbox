import { describe, expect, it, vi } from 'vitest'

import {
  BrowserTerminalAttachment,
  BrowserTerminalProjectionRenderTask,
} from './browserTerminalRenderer'
import type { TerminalProjection, TerminalTextStyle } from './terminalModel'

function surface(): HTMLElement {
  return document.createElement('div')
}

const STYLE: TerminalTextStyle = Object.freeze({
  foreground: 'red',
  background: null,
  bold: false,
  dim: false,
  italic: false,
  underline: false,
  inverse: false,
})

function projection(runCount: number): TerminalProjection {
  return {
    lines: [
      {
        row: 0,
        runs: Array.from({ length: runCount }, (_, column) => ({
          column,
          width: 1,
          text: 'X',
          style: STYLE,
        })),
      },
    ],
  } as unknown as TerminalProjection
}

describe('BrowserTerminalAttachment', () => {
  it('renders terminal plaintext with textContent and closed presentation classes', async () => {
    const element = surface()
    const attachment = new BrowserTerminalAttachment(element, vi.fn())

    await attachment.enqueueFrame(
      new TextEncoder().encode('\u001b[31m<terminal-output>'),
    )

    expect(element.textContent).toContain('<terminal-output>')
    expect(element.querySelector('img')).toBeNull()
    expect(element.querySelector('.waw-terminal-line')).not.toBeNull()
    expect(element.querySelector('.waw-terminal-fg-red')).not.toBeNull()
  })

  it('clears committed DOM and rejects future output when an attachment is cancelled', async () => {
    const element = surface()
    const fenced = vi.fn()
    const attachment = new BrowserTerminalAttachment(element, fenced)
    await attachment.enqueueFrame(new TextEncoder().encode('sensitive output'))
    expect(element.textContent).toContain('sensitive output')

    attachment.cancelAttachment()

    expect(element.textContent).toBe('')
    expect(fenced).toHaveBeenCalledWith(
      expect.objectContaining({ reason: 'ATTACHMENT_CANCELLED' }),
    )
    expect(() => attachment.enqueueFrame(new Uint8Array([0x41]))).toThrow()
  })

  it('does not erase a new owner surface after a reentrant cancellation fence', async () => {
    const element = surface()
    const fenced = vi.fn(() => {
      element.textContent = 'new owner content'
    })
    const attachment = new BrowserTerminalAttachment(element, fenced)
    await attachment.enqueueFrame(new TextEncoder().encode('old content'))

    attachment.cancelAttachment()

    expect(element.textContent).toBe('new owner content')
    expect(fenced).toHaveBeenCalledTimes(1)
  })

  it('uses textContent fallback to clear old DOM when a render commit throws', async () => {
    const element = surface()
    const fenced = vi.fn()
    const attachment = new BrowserTerminalAttachment(element, fenced)
    await attachment.enqueueFrame(new TextEncoder().encode('old plaintext'))
    Object.defineProperty(element, 'replaceChildren', {
      configurable: true,
      value: () => {
        throw new Error('render commit failed')
      },
    })

    await expect(
      attachment.enqueueFrame(new TextEncoder().encode('new plaintext')),
    ).rejects.toThrow()

    expect(element.childNodes).toHaveLength(0)
    expect(element.textContent).toBe('')
    expect(fenced).toHaveBeenCalledWith(
      expect.objectContaining({ reason: 'TERMINAL_RENDER_FAILED' }),
    )
  })

  it('uses textContent fallback during cancellation when replaceChildren always fails', async () => {
    const element = surface()
    const fenced = vi.fn()
    const attachment = new BrowserTerminalAttachment(element, fenced)
    await attachment.enqueueFrame(new TextEncoder().encode('old plaintext'))
    Object.defineProperty(element, 'replaceChildren', {
      configurable: true,
      value: () => {
        throw new Error('clear failed')
      },
    })

    attachment.cancelAttachment()

    expect(element.childNodes).toHaveLength(0)
    expect(element.textContent).toBe('')
    expect(fenced).toHaveBeenCalledTimes(1)
  })

  it('notifies the fence before reporting an unrecoverable surface clear failure', async () => {
    const element = surface()
    const fenced = vi.fn()
    const attachment = new BrowserTerminalAttachment(element, fenced)
    await attachment.enqueueFrame(new TextEncoder().encode('old plaintext'))
    Object.defineProperty(element, 'replaceChildren', {
      configurable: true,
      value: () => {
        throw new Error('clear failed')
      },
    })
    const descriptor = Object.getOwnPropertyDescriptor(
      Node.prototype,
      'textContent',
    )
    if (descriptor?.get === undefined || descriptor.set === undefined) {
      throw new Error('textContent descriptor is unavailable')
    }
    Object.defineProperty(element, 'textContent', {
      configurable: true,
      get: () => descriptor.get!.call(element),
      set: () => {
        throw new Error('fallback failed')
      },
    })

    expect(() => attachment.cancelAttachment()).toThrow(
      'terminal surface clearance failed',
    )
    expect(fenced).toHaveBeenCalledTimes(1)
  })

  it('clears old DOM and fences when DOM node construction throws', async () => {
    const element = surface()
    const fenced = vi.fn()
    const attachment = new BrowserTerminalAttachment(element, fenced)
    await attachment.enqueueFrame(new TextEncoder().encode('old plaintext'))
    const document = element.ownerDocument
    const createElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementationOnce(() => {
      throw new Error('node creation failed')
    })

    await expect(
      attachment.enqueueFrame(new TextEncoder().encode('new plaintext')),
    ).rejects.toThrow()

    expect(element.textContent).toBe('')
    expect(fenced).toHaveBeenCalledWith(
      expect.objectContaining({ reason: 'TERMINAL_RENDER_FAILED' }),
    )
    vi.restoreAllMocks()
    expect(createElement('div')).toBeInstanceOf(HTMLDivElement)
  })

  it('finishes a large projection across bounded scheduled render turns', async () => {
    const element = surface()
    const task = new BrowserTerminalProjectionRenderTask(
      element,
      projection(64),
      1,
      () => true,
    )
    const replaceChildren = vi.spyOn(element, 'replaceChildren')
    let now = 0
    const clock = () => now++

    expect(task.run(clock, 5)).toBe(false)
    expect(replaceChildren).not.toHaveBeenCalled()
    expect(task.run(clock, 500)).toBe(true)

    expect(replaceChildren).toHaveBeenCalledTimes(1)
    expect(element.textContent).toContain('X'.repeat(64))
  })

  it('makes a cancelled queued render inert before it can commit DOM', async () => {
    const element = surface()
    const attachment = new BrowserTerminalAttachment(element, vi.fn())
    const pending = attachment.enqueueFrame(
      new TextEncoder().encode('queued plaintext'),
    )

    attachment.cancelAttachment()
    await expect(pending).rejects.toThrow()
    await new Promise<void>((resolve) => globalThis.setTimeout(resolve, 0))

    expect(element.textContent).toBe('')
  })

  it('keeps a late manually scheduled render inert after cancellation', async () => {
    const element = surface()
    const task = new BrowserTerminalProjectionRenderTask(
      element,
      projection(64),
      1,
      () => true,
    )
    const replaceChildren = vi.spyOn(element, 'replaceChildren')
    let now = 0
    const clock = () => now++

    expect(task.run(clock, 5)).toBe(false)
    expect(replaceChildren).not.toHaveBeenCalled()

    task.cancel()
    const callsAfterCancel = replaceChildren.mock.calls.length
    expect(task.run(clock, 500)).toBe(true)

    expect(replaceChildren).toHaveBeenCalledTimes(callsAfterCancel)
    expect(element.textContent).toBe('')
  })

  it('clears DOM before forwarding an internal scheduler fence', async () => {
    const element = surface()
    const observed: string[] = []
    const attachment = new BrowserTerminalAttachment(element, () => {
      observed.push(element.textContent ?? '')
    })
    await attachment.enqueueFrame(new TextEncoder().encode('before fence'))
    expect(element.textContent).toContain('before fence')

    expect(() => attachment.enqueueFrame(new Uint8Array(65_537))).toThrow()

    expect(observed).toEqual([''])
    expect(element.textContent).toBe('')
  })
})
