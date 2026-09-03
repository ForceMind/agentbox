/**
 * Transport-independent Browser Terminal Security tokenizer foundation.
 *
 * No renderer, DOM, transport, admission, response, persistence or timers. The
 * caller admits complete output frames and repeatedly calls runTask with a pure,
 * monotonic millisecond clock (also when idle at nextDeadlineMs). Task budgets
 * are cooperative, checked before each byte; scheduling is the caller's job.
 * Returned tokens are data, never strings to write back into a VT interpreter.
 * A future renderer must implement/clamp typed operations inside its validated
 * viewport. Text must use its text model, never HTML or automatic link handling.
 *
 * NOT IMPLEMENTED: 50 ms/s attachment scheduling, three-window detach/cleanup,
 * logical-line deadline (no duration is specified), xterm or browser integration.
 * Sequence/frame limits fail closed until explicit reset; that is a core failure
 * boundary, not a decision about controller recovery or attachment admission.
 */

export const TERMINAL_LIMITS = Object.freeze({
  frameBytes: 32_768,
  frameControls: 256,
  sequenceBytes: 4096,
  sequenceMs: 100,
  taskBytes: 10_000,
  taskMs: 5,
  lineBytes: 32_768,
})

const CSI_FINALS = 'ABCDEFGHJKLMPSTfm@su' as const
type CsiFinal =
  | 'A'
  | 'B'
  | 'C'
  | 'D'
  | 'E'
  | 'F'
  | 'G'
  | 'H'
  | 'J'
  | 'K'
  | 'L'
  | 'M'
  | 'P'
  | 'S'
  | 'T'
  | 'f'
  | 'm'
  | '@'
  | 's'
  | 'u'

export type TerminalToken =
  | { readonly kind: 'text'; readonly text: string }
  | {
      readonly kind: 'control'
      readonly control: 'BS' | 'HT' | 'LF' | 'VT' | 'FF' | 'CR'
    }
  | {
      readonly kind: 'csi'
      readonly final: CsiFinal
      /** Exactly [0-9;?]{0,32}; interpretation/clamping belongs to the renderer. */
      readonly parameters: string
    }
  | { readonly kind: 'cursor'; readonly action: 'save' | 'restore' }
  | { readonly kind: 'alternate-screen'; readonly enabled: boolean }

export type TerminalTokenizerState = 'ready' | 'needs-reset' | 'destroyed'
export type TerminalTokenizerErrorCode =
  | 'TERMINAL_PARSE_LIMIT'
  | 'TERMINAL_TOKENIZER_RESET_REQUIRED'
  | 'TERMINAL_TOKENIZER_DESTROYED'
  | 'TERMINAL_TOKENIZER_BUSY'
  | 'TERMINAL_TOKENIZER_INVALID_FRAME'
  | 'TERMINAL_TOKENIZER_INVALID_CLOCK'

export class TerminalTokenizerError extends Error {
  constructor(readonly code: TerminalTokenizerErrorCode) {
    super(code)
    this.name = 'TerminalTokenizerError'
  }
}

export interface TerminalTaskResult {
  readonly tokens: readonly TerminalToken[]
  readonly consumedBytes: number
  readonly frameComplete: boolean
  readonly state: TerminalTokenizerState
  /** Local metadata only: never an ABWS GAP or an output cursor. */
  readonly status: 'TERMINAL_PARSE_LIMIT' | null
  /** Task-local, bounded by the byte/control limits; contains no payload. */
  readonly discardedControls: number
  readonly nextDeadlineMs: number | null
}

type Mode = 'ground' | 'escape' | 'escape-intermediate' | 'csi' | 'string'
interface Output {
  tokens: TerminalToken[]
  text: string
  discardedControls: number
  limited: boolean
}

export class TerminalTokenizer {
  private currentState: TerminalTokenizerState = 'ready'
  private running = false
  private lastTime = -Infinity
  // One copied pending frame is separate from parser carry. Consumed bytes are
  // zeroed; no raw logical line or string body is retained, even across tasks.
  private frame: Uint8Array | null = null
  private offset = 0
  private frameControls = 0
  private lineBytes = 0
  private droppingLine = false
  private suppressOutput = false
  private sequenceSuppressed = false
  private mode: Mode = 'ground'
  private sequenceStarted = 0
  private sequenceBytes = 0
  private parameters = ''
  private csiAllowed = false
  private osc = false
  private stringEscape = false
  private utf8Remaining = 0
  private utf8Value = 0
  private utf8Width = 0
  private utf8Started = 0
  private continuationMin = 0x80
  private continuationMax = 0xbf

  get state(): TerminalTokenizerState {
    return this.currentState
  }

  get nextDeadlineMs(): number | null {
    if (this.mode !== 'ground') {
      const started = this.utf8Remaining
        ? Math.min(this.sequenceStarted, this.utf8Started)
        : this.sequenceStarted
      return started + TERMINAL_LIMITS.sequenceMs
    }
    return this.utf8Remaining
      ? this.utf8Started + TERMINAL_LIMITS.sequenceMs
      : null
  }

  /** Copies a bounded frame; a pending frame must finish before another begins. */
  beginFrame(bytes: Uint8Array): void {
    this.assertReady()
    if (this.frame) throw new TerminalTokenizerError('TERMINAL_TOKENIZER_BUSY')
    if (
      !ArrayBuffer.isView(bytes) ||
      Object.prototype.toString.call(bytes) !== '[object Uint8Array]'
    ) {
      throw new TerminalTokenizerError('TERMINAL_TOKENIZER_INVALID_FRAME')
    }
    if (bytes.byteLength > TERMINAL_LIMITS.frameBytes) {
      this.fail()
      throw new TerminalTokenizerError('TERMINAL_PARSE_LIMIT')
    }
    this.frame = bytes.length ? new Uint8Array(bytes) : null
    this.offset = 0
    // A carried control sequence also occupies a slot in the new frame.
    this.frameControls = this.mode === 'ground' ? 0 : 1
  }

  runTask(clock: () => number): TerminalTaskResult {
    this.assertReady()
    this.running = true
    const output: Output = {
      tokens: [],
      text: '',
      discardedControls: 0,
      limited: false,
    }
    let consumedBytes = 0
    try {
      const started = this.readTime(clock)
      let now = started
      while (this.currentState === 'ready') {
        const deadline = this.nextDeadlineMs
        if (deadline !== null && now >= deadline) {
          this.limit(output)
          break
        }
        if (
          !this.frame ||
          consumedBytes >= TERMINAL_LIMITS.taskBytes ||
          now - started >= TERMINAL_LIMITS.taskMs
        ) {
          break
        }
        const byte = this.frame[this.offset]
        this.frame[this.offset++] = 0
        consumedBytes++
        if (this.offset === this.frame.length) {
          this.frame = null
          this.offset = 0
        }
        this.consumeByte(byte, now, output)
        now = this.readTime(clock)
      }
      this.flush(output)
      return {
        tokens: output.tokens,
        consumedBytes,
        frameComplete: this.frame === null,
        state: this.currentState,
        status: output.limited ? 'TERMINAL_PARSE_LIMIT' : null,
        discardedControls: output.discardedControls,
        nextDeadlineMs: this.nextDeadlineMs,
      }
    } finally {
      this.running = false
    }
  }

  /** Explicit caller decision, not automatic recovery/admission. Clears carry. */
  reset(): void {
    this.assertNotRunning()
    if (this.currentState === 'destroyed') {
      throw new TerminalTokenizerError('TERMINAL_TOKENIZER_DESTROYED')
    }
    this.clear()
    this.lastTime = -Infinity
    this.currentState = 'ready'
  }

  destroy(): void {
    this.assertNotRunning()
    this.clear()
    this.lastTime = -Infinity
    this.currentState = 'destroyed'
  }

  private assertNotRunning(): void {
    if (this.running)
      throw new TerminalTokenizerError('TERMINAL_TOKENIZER_BUSY')
  }

  private assertReady(): void {
    this.assertNotRunning()
    if (this.currentState !== 'ready') {
      throw new TerminalTokenizerError(
        this.currentState === 'destroyed'
          ? 'TERMINAL_TOKENIZER_DESTROYED'
          : 'TERMINAL_TOKENIZER_RESET_REQUIRED',
      )
    }
  }

  private readTime(clock: () => number): number {
    let value: number
    try {
      value = clock()
    } catch {
      this.fail()
      throw new TerminalTokenizerError('TERMINAL_TOKENIZER_INVALID_CLOCK')
    }
    if (!Number.isFinite(value) || value < 0 || value < this.lastTime) {
      this.fail()
      throw new TerminalTokenizerError('TERMINAL_TOKENIZER_INVALID_CLOCK')
    }
    this.lastTime = value
    return value
  }

  private clearUtf8(): void {
    this.utf8Remaining = this.utf8Value = this.utf8Width = this.utf8Started = 0
    this.continuationMin = 0x80
    this.continuationMax = 0xbf
  }

  private clearSequence(): void {
    this.mode = 'ground'
    this.sequenceStarted = this.sequenceBytes = 0
    this.parameters = ''
    this.csiAllowed = this.osc = this.stringEscape = false
    this.sequenceSuppressed = false
  }

  private clear(): void {
    this.frame?.fill(0)
    this.frame = null
    this.offset = this.frameControls = this.lineBytes = 0
    this.droppingLine = false
    this.suppressOutput = false
    this.clearSequence()
    this.clearUtf8()
  }

  private fail(): void {
    this.clear()
    this.currentState = 'needs-reset'
  }

  private limit(output: Output): void {
    output.limited = true
    this.fail()
  }

  private countControl(output: Output): boolean {
    if (++this.frameControls > TERMINAL_LIMITS.frameControls) {
      this.limit(output)
      return false
    }
    return true
  }

  private flush(output: Output): void {
    if (output.text) {
      output.tokens.push({ kind: 'text', text: output.text })
      output.text = ''
    }
  }

  private emit(output: Output, token: TerminalToken): void {
    if (this.suppressOutput || this.sequenceSuppressed) {
      output.discardedControls++
      return
    }
    this.flush(output)
    output.tokens.push(token)
  }

  private consumeByte(byte: number, now: number, output: Output): void {
    if (
      this.mode !== 'ground' &&
      ++this.sequenceBytes > TERMINAL_LIMITS.sequenceBytes
    ) {
      this.limit(output)
      return
    }
    if (!this.droppingLine && ++this.lineBytes > TERMINAL_LIMITS.lineBytes) {
      this.lineBytes = 0
      this.droppingLine = true
      output.limited = true
    }
    // Line truncation suppresses output, not the bounded lexer: otherwise
    // control/sequence limits could be bypassed by entering drop-through-LF.
    // An operation spanning omitted bytes stays suppressed until it finishes.
    this.suppressOutput = this.droppingLine
    if (this.suppressOutput && this.mode !== 'ground') {
      this.sequenceSuppressed = true
    }
    this.decodeByte(byte, now, output)
    this.suppressOutput = false
    if (byte === 0x0a) {
      this.lineBytes = 0
      this.droppingLine = false
    }
  }

  private decodeByte(byte: number, now: number, output: Output): void {
    if (this.utf8Remaining) {
      if (byte >= this.continuationMin && byte <= this.continuationMax) {
        this.utf8Value = (this.utf8Value << 6) | (byte & 0x3f)
        this.utf8Remaining--
        this.continuationMin = 0x80
        this.continuationMax = 0xbf
        if (!this.utf8Remaining) {
          const value = this.utf8Value
          const width = this.utf8Width
          const started = this.utf8Started
          this.clearUtf8()
          this.consumeScalar(value, width, started, output)
        }
        return
      }
      // One replacement for the malformed prefix; classify the offending byte
      // again at a code-point boundary, without counting/consuming it twice.
      this.clearUtf8()
      this.consumeScalar(0xfffd, 0, now, output)
    }
    if (byte < 0xa0) {
      // Only here can a raw C1 byte be a control, never inside valid UTF-8.
      this.consumeScalar(byte, 1, now, output)
    } else if (byte >= 0xc2 && byte <= 0xf4) {
      this.utf8Started = now
      this.utf8Width = byte <= 0xdf ? 2 : byte <= 0xef ? 3 : 4
      this.utf8Remaining = this.utf8Width - 1
      this.utf8Value =
        byte & (this.utf8Width === 2 ? 0x1f : this.utf8Width === 3 ? 0x0f : 7)
      this.continuationMin = byte === 0xe0 ? 0xa0 : byte === 0xf0 ? 0x90 : 0x80
      this.continuationMax = byte === 0xed ? 0x9f : byte === 0xf4 ? 0x8f : 0xbf
    } else {
      this.consumeScalar(0xfffd, 1, now, output)
    }
  }

  private startSequence(mode: Mode, width: number, now: number): void {
    this.mode = mode
    this.sequenceBytes = width
    this.sequenceStarted = now
    this.sequenceSuppressed = this.suppressOutput
  }

  private consumeScalar(
    value: number,
    width: number,
    now: number,
    output: Output,
  ): void {
    if (this.mode === 'string') {
      if (
        value === 0x9c ||
        (this.osc && value === 7) ||
        (this.stringEscape && value === 0x5c)
      ) {
        this.clearSequence()
      } else {
        this.stringEscape = value === 0x1b
      }
      return
    }
    // ESC and raw/decoded C1 introducers interrupt every non-string pending
    // state; their body cannot fall through as ordinary text. C1 families stay
    // inert. Keep the oldest carry deadline/bytes so re-entry cannot renew them.
    if (
      value === 0x1b ||
      [0x90, 0x98, 0x9b, 0x9d, 0x9e, 0x9f].includes(value)
    ) {
      if (!this.countControl(output)) return
      const mode = value === 0x1b ? 'escape' : value === 0x9b ? 'csi' : 'string'
      if (this.mode === 'ground') this.startSequence(mode, width, now)
      else this.mode = mode
      this.parameters = ''
      this.csiAllowed = false
      this.stringEscape = false
      this.osc = value === 0x9d
      if (mode === 'string') output.discardedControls++
      return
    }
    if (this.mode === 'csi') {
      if (value >= 0x40 && value <= 0x7e) {
        const final = String.fromCodePoint(value)
        if (this.csiAllowed && CSI_FINALS.includes(final)) {
          this.emit(output, {
            kind: 'csi',
            final: final as CsiFinal,
            parameters: this.parameters,
          })
        } else if (
          this.csiAllowed &&
          this.parameters === '?1049' &&
          (final === 'h' || final === 'l')
        ) {
          this.emit(output, {
            kind: 'alternate-screen',
            enabled: final === 'h',
          })
        } else {
          output.discardedControls++
        }
        this.clearSequence()
      } else if (
        this.parameters.length < 32 &&
        ((value >= 0x30 && value <= 0x39) || value === 0x3b || value === 0x3f)
      ) {
        this.parameters += String.fromCodePoint(value)
      } else {
        this.csiAllowed = false
      }
      return
    }
    if (this.mode === 'escape-intermediate') {
      if (value < 0x20 || value > 0x2f) this.clearSequence()
      return
    }
    if (this.mode === 'escape') {
      if (value === 0x5b) {
        this.mode = 'csi'
        this.csiAllowed = true
      } else if ([0x5d, 0x50, 0x5e, 0x5f, 0x58].includes(value)) {
        this.mode = 'string'
        this.osc = value === 0x5d
        output.discardedControls++
      } else if (value >= 0x20 && value <= 0x2f) {
        this.mode = 'escape-intermediate'
        output.discardedControls++
      } else {
        if (value === 0x37 || value === 0x38) {
          this.emit(output, {
            kind: 'cursor',
            action: value === 0x37 ? 'save' : 'restore',
          })
        } else {
          output.discardedControls++
        }
        this.clearSequence()
      }
      return
    }
    if (value < 0x20 || (value >= 0x7f && value <= 0x9f)) {
      if (!this.countControl(output)) return
      if (value >= 8 && value <= 13) {
        const controls = ['BS', 'HT', 'LF', 'VT', 'FF', 'CR'] as const
        this.emit(output, { kind: 'control', control: controls[value - 8] })
      } else {
        output.discardedControls++
      }
      return
    }
    if (
      (value >= 0x200b && value <= 0x200f) ||
      value === 0x2060 ||
      value === 0xfeff
    ) {
      if (this.countControl(output)) output.discardedControls++
    } else if (
      (value >= 0x202a && value <= 0x202e) ||
      (value >= 0x2066 && value <= 0x2069)
    ) {
      if (!this.suppressOutput) {
        output.text += `\\u{${value.toString(16).toUpperCase()}}`
      }
    } else {
      if (!this.suppressOutput) output.text += String.fromCodePoint(value)
    }
  }
}
