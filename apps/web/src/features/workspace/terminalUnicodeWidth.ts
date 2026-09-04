import {
  TERMINAL_BIDI_CONTROL_RANGES,
  TERMINAL_COMBINING_RANGES,
  TERMINAL_DEFAULT_IGNORABLE_RANGES,
  TERMINAL_EMOJI_MODIFIER_BASE_RANGES,
  TERMINAL_EMOJI_MODIFIER_RANGES,
  TERMINAL_HANGUL_L_RANGES,
  TERMINAL_HANGUL_LV_RANGES,
  TERMINAL_HANGUL_LVT_RANGES,
  TERMINAL_HANGUL_T_RANGES,
  TERMINAL_HANGUL_V_RANGES,
  TERMINAL_WIDE_RANGES,
  type UnicodeRange,
} from './terminalUnicodeWidthData'

export type TerminalScalarWidth = 0 | 1 | 2
export type TerminalHangulRole = 'L' | 'V' | 'T' | 'LV' | 'LVT'

function inRanges(value: number, ranges: readonly UnicodeRange[]): boolean {
  let low = 0
  let high = ranges.length - 1
  while (low <= high) {
    const middle = (low + high) >>> 1
    const [start, end] = ranges[middle]
    if (value < start) high = middle - 1
    else if (value > end) low = middle + 1
    else return true
  }
  return false
}

export function isTerminalBidiControl(value: number): boolean {
  return inRanges(value, TERMINAL_BIDI_CONTROL_RANGES)
}

export function isTerminalDefaultIgnorable(value: number): boolean {
  return inRanges(value, TERMINAL_DEFAULT_IGNORABLE_RANGES)
}

export function isTerminalEmojiModifier(value: number): boolean {
  return inRanges(value, TERMINAL_EMOJI_MODIFIER_RANGES)
}

export function isTerminalEmojiModifierBase(value: number): boolean {
  return inRanges(value, TERMINAL_EMOJI_MODIFIER_BASE_RANGES)
}

export function terminalHangulRole(value: number): TerminalHangulRole | null {
  if (inRanges(value, TERMINAL_HANGUL_L_RANGES)) return 'L'
  if (inRanges(value, TERMINAL_HANGUL_V_RANGES)) return 'V'
  if (inRanges(value, TERMINAL_HANGUL_T_RANGES)) return 'T'
  if (inRanges(value, TERMINAL_HANGUL_LV_RANGES)) return 'LV'
  if (inRanges(value, TERMINAL_HANGUL_LVT_RANGES)) return 'LVT'
  return null
}

export function joinsHangulCluster(
  previous: TerminalHangulRole | null,
  current: TerminalHangulRole | null,
): boolean {
  if (!previous || !current) return false
  if (previous === 'L') {
    return (
      current === 'L' ||
      current === 'V' ||
      current === 'LV' ||
      current === 'LVT'
    )
  }
  if (previous === 'LV' || previous === 'V') {
    return current === 'V' || current === 'T'
  }
  return (previous === 'LVT' || previous === 'T') && current === 'T'
}

/**
 * Returns the fixed UCD-backed terminal width for one Unicode scalar.
 *
 * The tokenizer has already removed its closed invisible table and converted
 * bidi controls to visible ASCII markers. This helper still rejects controls,
 * surrogates and out-of-range values so a forged token cannot bypass that
 * boundary. It does not call Intl.Segmenter, canvas/font measurement, locale
 * APIs, or runtime Unicode-property regular expressions.
 */
export function terminalScalarWidth(value: number): TerminalScalarWidth | null {
  if (
    !Number.isInteger(value) ||
    value < 0x20 ||
    value > 0x10ffff ||
    (value >= 0x7f && value <= 0x9f) ||
    (value >= 0xd800 && value <= 0xdfff) ||
    isTerminalBidiControl(value) ||
    isTerminalDefaultIgnorable(value)
  ) {
    return null
  }
  if (isTerminalEmojiModifier(value) || isTerminalEmojiModifierBase(value)) {
    return 2
  }
  if (inRanges(value, TERMINAL_COMBINING_RANGES)) return 0
  if (inRanges(value, TERMINAL_WIDE_RANGES)) return 2
  return 1
}
