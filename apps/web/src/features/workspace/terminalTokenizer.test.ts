import { describe, expect, it } from 'vitest'
import {
  TERMINAL_LIMITS,
  TerminalTokenizer,
  TerminalTokenizerError,
  type TerminalTaskResult,
  type TerminalToken,
} from './terminalTokenizer'

const utf8 = (text: string) => new TextEncoder().encode(text)
const join = (...parts: Uint8Array[]) =>
  new Uint8Array(parts.flatMap((part) => [...part]))
const textOf = (tokens: readonly TerminalToken[]) =>
  tokens
    .flatMap((token) => (token.kind === 'text' ? [token.text] : []))
    .join('')
const normalize = (tokens: readonly TerminalToken[]): TerminalToken[] => {
  const result: TerminalToken[] = []
  for (const token of tokens) {
    const previous = result.at(-1)
    if (token.kind === 'text' && previous?.kind === 'text') {
      result[result.length - 1] = {
        kind: 'text',
        text: previous.text + token.text,
      }
    } else {
      result.push(token)
    }
  }
  return result
}

function feed(
  parser: TerminalTokenizer,
  bytes: Uint8Array,
  now = 0,
): TerminalTaskResult[] {
  parser.beginFrame(bytes)
  const results: TerminalTaskResult[] = []
  do {
    results.push(parser.runTask(() => now))
  } while (!results.at(-1)!.frameComplete)
  return results
}

function parse(bytes: Uint8Array): TerminalToken[] {
  return normalize(
    feed(new TerminalTokenizer(), bytes).flatMap((result) => result.tokens),
  )
}

function splitEverywhere(bytes: Uint8Array, expected: TerminalToken[]): void {
  for (let split = 0; split <= bytes.length; split++) {
    const parser = new TerminalTokenizer()
    const tokens = [
      ...feed(parser, bytes.slice(0, split)).flatMap((result) => result.tokens),
      ...feed(parser, bytes.slice(split)).flatMap((result) => result.tokens),
    ]
    expect(normalize(tokens), `split ${split}`).toEqual(expected)
    expect(parser.state).toBe('ready')
    expect(parser.nextDeadlineMs).toBeNull()
  }
}

describe('incremental terminal tokenizer foundation', () => {
  it('preserves valid non-ASCII C1 continuation bytes at every split', () => {
    const text = '项目：中文 Ελληνικά שלום عربي 😀 € Ж \u009f'.replace(
      '\u009f',
      '',
    )
    splitEverywhere(utf8(text), [{ kind: 'text', text }])
    // Every possible C1 byte occurs as the valid continuation of a scalar.
    const scalars = Array.from({ length: 32 }, (_, i) =>
      String.fromCodePoint(0x400 + i),
    ).join('')
    splitEverywhere(utf8(scalars), [{ kind: 'text', text: scalars }])
  })

  it('retains multibyte scalars and ESC/CSI state through one-byte frames', () => {
    const bytes = utf8('中\x1b[38;5;123m文😀\x1b7\x1b8\n')
    const parser = new TerminalTokenizer()
    const tokens = [...bytes].flatMap((byte) =>
      feed(parser, new Uint8Array([byte])).flatMap((result) => result.tokens),
    )
    expect(normalize(tokens)).toEqual(parse(bytes))
    expect(parser.nextDeadlineMs).toBeNull()
  })

  it('emits only the six typed C0 controls; drops all other C0 and DEL', () => {
    const bytes = new Uint8Array(
      [...Array(32).keys()].filter((byte) => byte !== 0x1b).concat(0x7f),
    )
    const results = feed(new TerminalTokenizer(), bytes)
    expect(results[0].tokens).toEqual(
      ['BS', 'HT', 'LF', 'VT', 'FF', 'CR'].map((control) => ({
        kind: 'control',
        control,
      })),
    )
    expect(results[0].discardedControls).toBe(26)
  })

  it.each([...'ABCDEFGHJKLMPSTfm@su'])(
    'allows only typed CSI %s with bounded parameters',
    (final) => {
      splitEverywhere(utf8(`a\x1b[12;?3${final}b`), [
        { kind: 'text', text: 'a' },
        {
          kind: 'csi',
          final: final as Extract<TerminalToken, { kind: 'csi' }>['final'],
          parameters: '12;?3',
        },
        { kind: 'text', text: 'b' },
      ])
    },
  )

  it('allows only exact alternate-screen mode changes and ESC cursor save/restore', () => {
    expect(parse(utf8('\x1b[?1049h\x1b[?1049l\x1b7\x1b8'))).toEqual([
      { kind: 'alternate-screen', enabled: true },
      { kind: 'alternate-screen', enabled: false },
      { kind: 'cursor', action: 'save' },
      { kind: 'cursor', action: 'restore' },
    ])
  })

  it.each([
    '\x1b[?2004h',
    '\x1b[?2004l',
    '\x1b[200~',
    '\x1b[201~',
    '\x1b[6n',
    '\x1b[c',
    '\x1b[18t',
    '\x1b[8;20;40t',
    '\x1b[?1000h',
    '\x1b[?1004h',
    '\x1b[4h',
    '\x1b[1049h',
    '\x1b[?1049;1h',
    '\x1b[?01049h',
    '\x1b[>0c',
    '\x1b[1:2m',
    '\x1b[1 m',
    `\x1b[${'1'.repeat(33)}m`,
    '\x1bc',
    '\x1b(B',
  ])(
    'discards denied mode, query, resize or malformed CSI/ESC %j',
    (sequence) => {
      splitEverywhere(utf8(`left${sequence}right`), [
        { kind: 'text', text: 'leftright' },
      ])
    },
  )

  it('accepts the exact 32-character parameter bound', () => {
    expect(parse(utf8(`\x1b[${'1'.repeat(32)}m`))).toEqual([
      { kind: 'csi', final: 'm', parameters: '1'.repeat(32) },
    ])
  })

  it.each([
    '\x1b]0;',
    '\x1b]2;',
    '\x1b]8;;',
    '\x1b]52;c;',
    '\x1bP',
    '\x1b_',
    '\x1b^',
    '\x1bX',
  ])(
    'consumes malicious string body %j and embedded controls through ST',
    (intro) => {
      const payload = `${intro}https://evil.invalid/\x1b[?1049h\x1b[6n<svg>CANARY😀`
      splitEverywhere(utf8(`safe${payload}\x1b\\tail`), [
        { kind: 'text', text: 'safetail' },
      ])
    },
  )

  it.each([0x90, 0x98, 0x9d, 0x9e, 0x9f])(
    'keeps raw/encoded C1 family %i completely inert',
    (intro) => {
      for (const start of [
        new Uint8Array([intro]),
        utf8(String.fromCodePoint(intro)),
      ]) {
        for (const end of [
          new Uint8Array([0x9c]),
          utf8('\u009c'),
          utf8('\x1b\\'),
        ]) {
          splitEverywhere(
            join(utf8('a'), start, utf8('CANARY\x1b[31m😀'), end, utf8('z')),
            [{ kind: 'text', text: 'az' }],
          )
        }
      }
    },
  )

  it('consumes raw/encoded C1 CSI instead of allowing its operations', () => {
    for (const intro of [new Uint8Array([0x9b]), utf8('\u009b')]) {
      splitEverywhere(join(utf8('a'), intro, utf8('?1049hz')), [
        { kind: 'text', text: 'az' },
      ])
      splitEverywhere(join(utf8('a'), intro, utf8('31mz')), [
        { kind: 'text', text: 'az' },
      ])
    }
  })

  it.each(['\x1b', '\x1b[12;', '\x1b(', '\x1b[>'])(
    'keeps raw/encoded C1 families inert inside pending state %j',
    (prefix) => {
      for (const value of [0x90, 0x98, 0x9b, 0x9d, 0x9e, 0x9f]) {
        for (const intro of [
          new Uint8Array([value]),
          utf8(String.fromCodePoint(value)),
        ]) {
          const body = value === 0x9b ? '?1049h' : '52;c;CANARY\x1b[31m\x1b\\'
          splitEverywhere(
            join(utf8(`safe${prefix}`), intro, utf8(`${body}tail`)),
            [{ kind: 'text', text: 'safetail' }],
          )
        }
      }
    },
  )

  it('does not renew carry bytes/deadlines when a C1 introducer interrupts a pending sequence', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('\x1b[12;'), 0)
    feed(parser, utf8('\u009d52;c;CANARY'), 99)
    expect(parser.nextDeadlineMs).toBe(100)
    expect(parser.runTask(() => 100).state).toBe('needs-reset')
    parser.reset()
    feed(parser, utf8(`\x1b[${'1'.repeat(4093)}`))
    expect(feed(parser, new Uint8Array([0x9d]))[0].state).toBe('ready')
    expect(feed(parser, utf8('\x07TAIL'))[0]).toMatchObject({
      consumedBytes: 1,
      state: 'needs-reset',
      status: 'TERMINAL_PARSE_LIMIT',
      tokens: [],
    })
  })

  it.each(['\x1b', '\x1b[12;', '\x1b('])(
    'handles valid UTF-8 continuation bytes before raw C1 classification in pending state %j',
    (prefix) => {
      for (const scalar of ['М', 'Н', 'Л', '\u101d', '\u{1001d}']) {
        splitEverywhere(utf8(`${prefix}${scalar}\x1b\\SAFE`), [
          { kind: 'text', text: 'SAFE' },
        ])
      }
    },
  )

  it.each(['\x1b', '\x1b[12;', '\x1b('])(
    'consumes denied ESC families after re-entry in pending state %j',
    (prefix) => {
      for (const sequence of [
        '\x1b]52;c;CANARY\x07',
        '\x1b]8;;CANARY\x1b\\',
        '\x1bPCANARY\x1b\\',
        '\x1b_CANARY\x1b\\',
        '\x1b^CANARY\x1b\\',
        '\x1bXCANARY\x1b\\',
        '\x1b[?2004h',
        '\x1b[6n',
      ]) {
        splitEverywhere(utf8(`safe${prefix}${sequence}tail`), [
          { kind: 'text', text: 'safetail' },
        ])
      }
    },
  )

  it('does not renew carry limits on repeated ESC re-entry across frames', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('\x1b[12;'), 0)
    feed(parser, utf8('\x1b]52;c;CANARY'), 99)
    expect(parser.nextDeadlineMs).toBe(100)
    expect(parser.runTask(() => 100).state).toBe('needs-reset')
    parser.reset()
    feed(parser, utf8(`\x1b[${'1'.repeat(4093)}`))
    expect(feed(parser, utf8('\x1b'))[0].state).toBe('ready')
    expect(feed(parser, utf8(']CANARY'))[0]).toMatchObject({
      consumedBytes: 1,
      state: 'needs-reset',
      status: 'TERMINAL_PARSE_LIMIT',
      tokens: [],
    })
  })

  it('discards every non-introducing raw and UTF-8 encoded C1 scalar', () => {
    const ordinary = Array.from({ length: 32 }, (_, i) => i + 0x80).filter(
      (value) => ![0x90, 0x98, 0x9b, 0x9d, 0x9e, 0x9f].includes(value),
    )
    expect(parse(new Uint8Array(ordinary))).toEqual([])
    expect(parse(utf8(String.fromCodePoint(...ordinary)))).toEqual([])
  })

  it('recognizes BEL only as an OSC terminator and preserves valid UTF-8 ST continuations', () => {
    expect(parse(utf8('a\x1b]52;c;secret\x07b'))).toEqual([
      { kind: 'text', text: 'ab' },
    ])
    expect(parse(utf8('a\x1bPsecret\x07stillsecret\x1b\\b'))).toEqual([
      { kind: 'text', text: 'ab' },
    ])
    // U+041C encodes as D0 9C; that 9C must not terminate the string.
    splitEverywhere(utf8('a\x1b]8;;Мsecret\x1b\\b'), [
      { kind: 'text', text: 'ab' },
    ])
  })

  it('renders every bidi control visibly and removes only the fixed invisible table', () => {
    const bidi = [
      ...Array.from({ length: 5 }, (_, i) => 0x202a + i),
      ...Array.from({ length: 4 }, (_, i) => 0x2066 + i),
    ]
    const invisible = [0x200b, 0x200c, 0x200d, 0x200e, 0x200f, 0x2060, 0xfeff]
    const text = `项目 שלום${String.fromCodePoint(...bidi)}عربي${String.fromCodePoint(...invisible)}end`
    const expected = `项目 שלום${bidi.map((value) => `\\u{${value.toString(16).toUpperCase()}}`).join('')}عربيend`
    splitEverywhere(utf8(text), [{ kind: 'text', text: expected }])
  })

  it.each([
    [0xc0, 0xaf],
    [0xc1, 0xbf],
    [0xe0, 0x80, 0xaf],
    [0xed, 0xa0, 0x80],
    [0xf0, 0x80, 0x80, 0xaf],
    [0xf4, 0x90, 0x80, 0x80],
    [0xf5, 0x80, 0x80, 0x80],
    [0xff],
    [0xc2, 0x41],
    [0xe2, 0x28, 0xa1],
  ])(
    'resynchronizes malformed UTF-8 %j with bounded replacement text',
    (...malformed) => {
      // A malformed prefix can expose a raw C1 string introducer at the new
      // code-point boundary (F4 90...). Explicit ST closes that denied body.
      const bytes = join(new Uint8Array(malformed), utf8('\x1b\\safe'))
      const expected = parse(bytes)
      splitEverywhere(bytes, expected)
      const text = textOf(expected)
      expect(text).toContain('\ufffd')
      expect(text.endsWith('safe')).toBe(true)
      expect(text.length).toBeLessThanOrEqual(bytes.length)
      for (const scalar of text) {
        const value = scalar.codePointAt(0)!
        expect(
          value >= 0x20 &&
            !(value >= 0x7f && value <= 0x9f) &&
            !(value >= 0xd800 && value <= 0xdfff),
        ).toBe(true)
      }
    },
  )

  it('reclassifies an offending ESC after invalid UTF-8 without leaking denied string data', () => {
    expect(
      parse(join(new Uint8Array([0xe2]), utf8('\x1b]52;c;CANARY\x07safe'))),
    ).toEqual([{ kind: 'text', text: '\ufffdsafe' }])
  })

  it.each([
    utf8('\x1b'),
    utf8('\x1b[1'),
    utf8('\x1b]52;c;secret'),
    new Uint8Array([0xf0, 0x9f]),
  ])(
    'fails closed on an incomplete sequence at its exact deadline',
    (bytes) => {
      const parser = new TerminalTokenizer()
      feed(parser, bytes, 10)
      expect(parser.nextDeadlineMs).toBe(110)
      expect(parser.runTask(() => 109).status).toBeNull()
      const expired = parser.runTask(() => 110)
      expect(expired).toMatchObject({
        status: 'TERMINAL_PARSE_LIMIT',
        state: 'needs-reset',
        frameComplete: true,
        nextDeadlineMs: null,
      })
      expect(expired.tokens).toEqual([])
      expect(() => parser.beginFrame(utf8('secret tail'))).toThrow(
        'TERMINAL_TOKENIZER_RESET_REQUIRED',
      )
    },
  )

  it('does not renew the sequence deadline when frames arrive or tasks yield', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('\x1b]'), 0)
    feed(parser, utf8('payload'), 99)
    expect(parser.nextDeadlineMs).toBe(100)
    expect(parser.runTask(() => 100).state).toBe('needs-reset')
  })

  it('accepts a 4096-byte complete string and fails closed at byte 4097', () => {
    const atLimit = utf8(`\x1b]${'x'.repeat(4093)}\x07`)
    expect(atLimit).toHaveLength(4096)
    expect(parse(atLimit)).toEqual([])
    const parser = new TerminalTokenizer()
    feed(parser, utf8(`\x1b]${'x'.repeat(4094)}`))
    const result = feed(parser, utf8('\x07CANARY'))[0]
    expect(result).toMatchObject({
      consumedBytes: 1,
      state: 'needs-reset',
      status: 'TERMINAL_PARSE_LIMIT',
      frameComplete: true,
    })
    expect(result.tokens).toEqual([])
  })

  it('caps each frame at 256 controls, including a carried control sequence', () => {
    const parser = new TerminalTokenizer()
    const result = feed(parser, utf8(`${'\x1b[31m'.repeat(257)}CANARY`))[0]
    expect(result.tokens).toHaveLength(256)
    expect(result.state).toBe('needs-reset')
    parser.reset()
    feed(parser, utf8('\x1b['))
    const carried = feed(parser, utf8(`m${'\x1b[31m'.repeat(256)}`))[0]
    expect(carried.tokens).toHaveLength(256)
    expect(carried.state).toBe('needs-reset')
  })

  it('keeps sequence failure closed when the same byte also overflows the logical line', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('a'.repeat(32_768 - 4096)))
    feed(parser, utf8(`\x1b]${'x'.repeat(4094)}`))
    const result = feed(parser, utf8('\x07\nnew line'))[0]
    expect(result).toMatchObject({
      consumedBytes: 1,
      status: 'TERMINAL_PARSE_LIMIT',
      state: 'needs-reset',
    })
    expect(result.tokens).toEqual([])
  })

  it('counts denied control floods and preserves the frame count across task yields', () => {
    expect(feed(new TerminalTokenizer(), new Uint8Array(257))[0]).toMatchObject(
      { discardedControls: 256, state: 'needs-reset' },
    )
    const parser = new TerminalTokenizer()
    parser.beginFrame(
      utf8(`${'x'.repeat(9999)}\x1b[31m${'\x1b[31m'.repeat(256)}`),
    )
    expect(parser.runTask(() => 0).consumedBytes).toBe(10_000)
    expect(parser.runTask(() => 0).state).toBe('needs-reset')
  })

  it('fails closed when the 257th frame control is the byte that overflows the logical line', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('a'.repeat(32_768 - 256)))
    const result = feed(parser, join(new Uint8Array(257), utf8('\nAFTER')))[0]
    expect(result).toMatchObject({
      consumedBytes: 257,
      state: 'needs-reset',
      status: 'TERMINAL_PARSE_LIMIT',
      tokens: [],
    })
    expect(() => parser.beginFrame(utf8('tail'))).toThrow(
      'TERMINAL_TOKENIZER_RESET_REQUIRED',
    )
  })

  it.each([new Uint8Array([0]), utf8('\u0080'), utf8('\u200b')])(
    'counts controls independently while a logical line is suppressed',
    (control) => {
      const parser = new TerminalTokenizer()
      feed(parser, utf8('x'.repeat(32_768)))
      const result = feed(
        parser,
        join(
          utf8('overflow'),
          ...Array.from({ length: 257 }, () => control),
          utf8('\nAFTER'),
        ),
      )[0]
      expect(result).toMatchObject({
        state: 'needs-reset',
        status: 'TERMINAL_PARSE_LIMIT',
        tokens: [],
      })
    },
  )

  it('keeps a control spanning suppressed bytes inert after LF without suppressing subsequent text', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('x'.repeat(32_768)))
    feed(parser, utf8('overflow\x1b['))
    expect(feed(parser, utf8('\nmAFTER'))[0].tokens).toEqual([
      { kind: 'text', text: 'AFTER' },
    ])
    parser.reset()
    feed(parser, utf8('x'.repeat(32_768)))
    feed(parser, utf8('overflow\x1b]52;c;CANARY'))
    expect(feed(parser, utf8('\nSTILL_CANARY\x07AFTER'))[0].tokens).toEqual([
      { kind: 'text', text: 'AFTER' },
    ])
  })

  it('rejects oversize frames without retaining input and requires explicit reset', () => {
    const parser = new TerminalTokenizer()
    expect(() =>
      parser.beginFrame(new Uint8Array(TERMINAL_LIMITS.frameBytes + 1)),
    ).toThrow('TERMINAL_PARSE_LIMIT')
    expect(parser.state).toBe('needs-reset')
    expect(parser.nextDeadlineMs).toBeNull()
    parser.reset()
    expect(feed(parser, utf8('safe'))[0].tokens).toEqual([
      { kind: 'text', text: 'safe' },
    ])
  })

  it('bounds a task to 10000 bytes and supports bounded continuation of a full frame', () => {
    const results = feed(new TerminalTokenizer(), utf8('x'.repeat(32_768)))
    expect(results.map((result) => result.consumedBytes)).toEqual([
      10_000, 10_000, 10_000, 2768,
    ])
    expect(textOf(results.flatMap((result) => result.tokens))).toHaveLength(
      32_768,
    )
    expect(results.every((result) => result.status === null)).toBe(true)
  })

  it('yields at 5 ms and preserves frame and DFA state for a subsequent task', () => {
    const parser = new TerminalTokenizer()
    parser.beginFrame(utf8('abcd😀tail'))
    let time = 0
    const first = parser.runTask(() => time++)
    expect(first).toMatchObject({
      consumedBytes: 5,
      frameComplete: false,
      state: 'ready',
    })
    expect(textOf(first.tokens)).toBe('abcd')
    const second = parser.runTask(() => time)
    expect(textOf(second.tokens)).toBe('😀tail')
    expect(second.frameComplete).toBe(true)
  })

  it('caps a raw logical line across frames and drops overflow through the next LF', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('x'.repeat(32_000)))
    const overflow = feed(
      parser,
      utf8(`${'y'.repeat(769)}\x1b[?1049hsecret`),
    )[0]
    expect(textOf(overflow.tokens)).toBe('y'.repeat(768))
    expect(overflow).toMatchObject({
      status: 'TERMINAL_PARSE_LIMIT',
      state: 'ready',
    })
    const recovered = feed(parser, utf8('still hidden\nnew line'))[0]
    expect(recovered.tokens).toEqual([{ kind: 'text', text: 'new line' }])
    expect(recovered.status).toBeNull()
  })

  it('counts raw UTF-8/control bytes toward the logical line and drops an overflowing LF', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('中'.repeat(10_000)))
    feed(parser, utf8(`\x1b[31m${'x'.repeat(2763)}`))
    const result = feed(parser, utf8('\nnext'))[0]
    expect(result.status).toBe('TERMINAL_PARSE_LIMIT')
    expect(result.tokens).toEqual([{ kind: 'text', text: 'next' }])
  })

  it('does not invent a logical-line deadline', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('partial line'), 0)
    expect(parser.nextDeadlineMs).toBeNull()
    expect(parser.runTask(() => 1_000_000).state).toBe('ready')
  })

  it('copies only the supplied byte range and never retains caller buffer aliases', () => {
    const bytes = utf8('beforeSAFEafter')
    const parser = new TerminalTokenizer()
    parser.beginFrame(bytes.subarray(6, 10))
    bytes.fill(0x1b)
    expect(parser.runTask(() => 0).tokens).toEqual([
      { kind: 'text', text: 'SAFE' },
    ])
    const caller = utf8('private')
    parser.beginFrame(caller)
    parser.destroy()
    expect(new TextDecoder().decode(caller)).toBe('private')
  })

  it('reset clears pending frames, UTF-8, string carry, line budget and failure state', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('x'.repeat(32_000)))
    feed(parser, utf8('\x1b]secret'))
    parser.beginFrame(utf8('unprocessed'))
    parser.reset()
    expect(parser.nextDeadlineMs).toBeNull()
    expect(parse(utf8('😀safe'))).toEqual(
      feed(parser, utf8('😀safe'))[0].tokens,
    )
    feed(parser, new Uint8Array([0xf0, 0x9f]))
    parser.reset()
    expect(feed(parser, utf8('ok'))[0].tokens).toEqual([
      { kind: 'text', text: 'ok' },
    ])
  })

  it('destroy is idempotent and permanently fences every parsing/reset entry point', () => {
    const parser = new TerminalTokenizer()
    feed(parser, utf8('\x1b]CANARY'))
    parser.destroy()
    parser.destroy()
    expect(parser.state).toBe('destroyed')
    expect(parser.nextDeadlineMs).toBeNull()
    for (const action of [
      () => parser.reset(),
      () => parser.beginFrame(utf8('tail')),
      () => parser.runTask(() => 0),
    ]) {
      expect(action).toThrow('TERMINAL_TOKENIZER_DESTROYED')
    }
  })

  it('rejects frame replacement and invalid frame types with fixed errors', () => {
    const parser = new TerminalTokenizer()
    expect(() => parser.beginFrame('CANARY' as unknown as Uint8Array)).toThrow(
      'TERMINAL_TOKENIZER_INVALID_FRAME',
    )
    parser.beginFrame(utf8('safe'))
    expect(() => parser.beginFrame(utf8('CANARY'))).toThrow(
      'TERMINAL_TOKENIZER_BUSY',
    )
    expect(parser.runTask(() => 0).tokens).toEqual([
      { kind: 'text', text: 'safe' },
    ])
  })

  it.each([NaN, Infinity, -1])(
    'fails closed for invalid clock value %j',
    (value) => {
      const parser = new TerminalTokenizer()
      expect(() => parser.runTask(() => value)).toThrow(
        'TERMINAL_TOKENIZER_INVALID_CLOCK',
      )
      expect(parser.state).toBe('needs-reset')
    },
  )

  it('rejects backwards/throwing/reentrant clocks without including exception payload', () => {
    for (const clock of [
      () => 0,
      () => {
        throw new Error('CANARY')
      },
    ]) {
      const parser = new TerminalTokenizer()
      parser.runTask(() => 1)
      expect(() => parser.runTask(clock)).toThrow(
        new TerminalTokenizerError('TERMINAL_TOKENIZER_INVALID_CLOCK'),
      )
      expect(parser.state).toBe('needs-reset')
    }
    const parser = new TerminalTokenizer()
    expect(() =>
      parser.runTask(() => {
        parser.reset()
        return 0
      }),
    ).toThrow('TERMINAL_TOKENIZER_INVALID_CLOCK')
    expect(parser.state).toBe('needs-reset')
  })
})
