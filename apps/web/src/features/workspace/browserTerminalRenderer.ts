import {
  TerminalScheduler,
  type TerminalRenderTask,
  type TerminalSchedulerFence,
} from './terminalScheduler'
import type { TerminalProjection, TerminalTextStyle } from './terminalModel'
import type {
  WAWBrowserTerminalSchedulerFactory,
  WAWBrowserTerminalSchedulerPort,
} from './wawBrowserController'

type RenderClock = () => number

const CLASS_PREFIX = 'waw-terminal'

function assertSurface(value: HTMLElement): void {
  if (
    !(value instanceof HTMLElement) ||
    typeof value.replaceChildren !== 'function' ||
    typeof value.ownerDocument?.createElement !== 'function'
  ) {
    throw new TypeError('A concrete terminal surface is required')
  }
}

function applyStyle(element: HTMLSpanElement, style: TerminalTextStyle): void {
  element.classList.add(`${CLASS_PREFIX}-run`)
  if (style.foreground !== null) {
    element.classList.add(`${CLASS_PREFIX}-fg-${style.foreground}`)
  }
  if (style.background !== null) {
    element.classList.add(`${CLASS_PREFIX}-bg-${style.background}`)
  }
  if (style.bold) element.classList.add(`${CLASS_PREFIX}-bold`)
  if (style.dim) element.classList.add(`${CLASS_PREFIX}-dim`)
  if (style.italic) element.classList.add(`${CLASS_PREFIX}-italic`)
  if (style.underline) element.classList.add(`${CLASS_PREFIX}-underline`)
  if (style.inverse) element.classList.add(`${CLASS_PREFIX}-inverse`)
}

/**
 * Builds a full model projection off-DOM. It commits exactly once, after every
 * row/run has been copied while the attachment epoch is still current.
 */
export class BrowserTerminalProjectionRenderTask implements TerminalRenderTask {
  readonly #surface: HTMLElement
  readonly #projection: TerminalProjection
  readonly #attachmentEpoch: number
  readonly #isCurrent: (epoch: number) => boolean
  readonly #fragment: DocumentFragment
  #lineIndex = 0
  #runIndex = 0
  #lastColumn = 0
  #line: HTMLDivElement | null = null
  #cancelled = false
  #committed = false

  constructor(
    surface: HTMLElement,
    projection: TerminalProjection,
    attachmentEpoch: number,
    isCurrent: (epoch: number) => boolean,
  ) {
    this.#surface = surface
    this.#projection = projection
    this.#attachmentEpoch = attachmentEpoch
    this.#isCurrent = isCurrent
    this.#fragment = surface.ownerDocument.createDocumentFragment()
  }

  cancel(): void {
    this.#cancelled = true
  }

  run(clock: RenderClock, absoluteDeadlineMs: number): boolean {
    if (this.#cancelled || !this.#isCurrent(this.#attachmentEpoch)) return true
    let now = clock()
    while (now < absoluteDeadlineMs) {
      if (this.#cancelled || !this.#isCurrent(this.#attachmentEpoch))
        return true
      if (this.#lineIndex >= this.#projection.lines.length) {
        if (!this.#committed) {
          this.#surface.replaceChildren(this.#fragment)
          this.#committed = true
        }
        return true
      }
      this.#renderOneStep()
      now = clock()
    }
    return false
  }

  #renderOneStep(): void {
    const source = this.#projection.lines[this.#lineIndex]
    if (source === undefined) return
    if (this.#line === null) {
      const line = this.#surface.ownerDocument.createElement('div')
      line.className = `${CLASS_PREFIX}-line`
      line.dataset.row = String(source.row)
      this.#line = line
      this.#runIndex = 0
      this.#lastColumn = 0
    }
    const run = source.runs[this.#runIndex]
    if (run !== undefined) {
      if (run.column > this.#lastColumn) {
        this.#line.append(
          this.#surface.ownerDocument.createTextNode(
            ' '.repeat(run.column - this.#lastColumn),
          ),
        )
      }
      const span = this.#surface.ownerDocument.createElement('span')
      applyStyle(span, run.style)
      // The model owns decoded plaintext only until projection release. DOM
      // textContent copies it without parsing it as markup or a URL.
      span.textContent = run.text
      this.#line.append(span)
      this.#lastColumn = run.column + run.width
      this.#runIndex += 1
      return
    }
    this.#fragment.append(this.#line)
    this.#line = null
    this.#lineIndex += 1
  }
}

/**
 * One controller attachment's DOM/scheduler owner. It has no ticket, key,
 * socket or persistent terminal state; cancellation clears every committed DOM
 * node before a future attachment may be created.
 */
export class BrowserTerminalAttachment implements WAWBrowserTerminalSchedulerPort {
  readonly #surface: HTMLElement
  readonly #onFence: (event: TerminalSchedulerFence) => void
  readonly #scheduler: TerminalScheduler
  #epoch = 1
  #closed = false

  constructor(
    surface: HTMLElement,
    onFence: (event: TerminalSchedulerFence) => void,
  ) {
    assertSurface(surface)
    this.#surface = surface
    this.#onFence = onFence
    this.#scheduler = new TerminalScheduler({
      createRenderTask: (projection, attachmentEpoch) =>
        new BrowserTerminalProjectionRenderTask(
          this.#surface,
          projection,
          attachmentEpoch,
          (epoch) => !this.#closed && epoch === this.#epoch,
        ),
      onFence: (event) => {
        let clearError: unknown = null
        try {
          this.#clear()
        } catch (error) {
          clearError = error
        }
        this.#onFence(event)
        if (clearError !== null) throw clearError
      },
    })
  }

  enqueueFrame(bytes: Uint8Array): Promise<void> {
    if (this.#closed) throw new Error('terminal attachment is closed')
    return this.#scheduler.enqueueFrame(bytes)
  }

  resize(columns: number, rows: number): void {
    if (this.#closed) throw new Error('terminal attachment is closed')
    this.#scheduler.resize(columns, rows)
  }

  cancelAttachment(): void {
    if (this.#closed) return
    this.#closed = true
    this.#epoch += 1
    let clearError: unknown = null
    try {
      // Clear before scheduler callbacks. A fence callback may synchronously
      // install a new owner, so never touch the surface after it returns.
      this.#clear()
    } catch (error) {
      clearError = error
    }
    let schedulerError: unknown = null
    try {
      this.#scheduler.cancelAttachment()
    } catch (error) {
      schedulerError = error
    }
    if (clearError !== null) throw clearError
    if (schedulerError !== null) throw schedulerError
  }

  #clear(): void {
    let cleared = false
    try {
      this.#surface.replaceChildren()
      cleared =
        this.#surface.childNodes.length === 0 &&
        this.#surface.textContent === ''
    } catch {
      // textContent below is a separate DOM primitive and can still remove the
      // previously committed terminal nodes after replaceChildren() fails.
    }
    if (!cleared) {
      try {
        this.#surface.textContent = ''
      } catch {
        // Verify below and surface the failure only after the external fence is
        // notified; hiding retained plaintext is never a successful cleanup.
      }
    }
    if (
      this.#surface.childNodes.length !== 0 ||
      this.#surface.textContent !== ''
    ) {
      throw new Error('terminal surface clearance failed')
    }
  }
}

/** Production code must use this explicit DOM renderer, never scheduler's test no-op. */
export function createBrowserTerminalSchedulerFactory(
  surface: HTMLElement,
): WAWBrowserTerminalSchedulerFactory {
  assertSurface(surface)
  return Object.freeze({
    create: (
      options: Parameters<WAWBrowserTerminalSchedulerFactory['create']>[0],
    ) => new BrowserTerminalAttachment(surface, options.onFence),
  })
}
