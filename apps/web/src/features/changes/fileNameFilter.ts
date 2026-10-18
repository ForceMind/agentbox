// Adapted from stablyai/orca src/shared/file-name-filter-tokens.ts at
// d378f49f17067c1949747d038a3b163fef5bbb41 (MIT). Copyright (c) 2026 Lovecast Inc.
// Changed: remove Orca clipboard dependency, add a local-only rename-source
// filter. This module cannot authorize Git paths or read repository content.

// AgentBox runs in a browser, not Orca's Electron clipboard runtime.
// Reject oversized code-unit input before measuring UTF-8.
const utf8Encoder = new TextEncoder()
function isClipboardTextByteLengthOverLimit(
  text: string,
  maxBytes: number,
): boolean {
  return text.length > maxBytes || utf8Encoder.encode(text).length > maxBytes
}

/** Explorer name-filter matching, shared so the host can filter a scan exactly like the renderer. */

export const FILE_NAME_FILTER_QUERY_MAX_BYTES = 2 * 1024

export function isFileNameFilterQueryTooLarge(
  query: string,
  maxBytes = FILE_NAME_FILTER_QUERY_MAX_BYTES,
): boolean {
  return isClipboardTextByteLengthOverLimit(query, maxBytes)
}

// Why: accepted pasted file-filter queries are still on a renderer hot path;
// tokenize whitespace directly instead of allocating a regex split array.
export function splitFileNameFilterTokens(query: string): string[] {
  const tokens: string[] = []
  let tokenStart = -1
  for (let index = 0; index <= query.length; index += 1) {
    const isEnd = index === query.length
    if (!isEnd && !isFileNameFilterWhitespace(query.charCodeAt(index))) {
      if (tokenStart === -1) {
        tokenStart = index
      }
      continue
    }
    if (tokenStart !== -1) {
      tokens.push(query.slice(tokenStart, index).toLowerCase())
      tokenStart = -1
    }
  }
  return tokens
}

function isFileNameFilterWhitespace(code: number): boolean {
  return (
    code === 32 ||
    (code >= 9 && code <= 13) ||
    code === 160 ||
    code === 5760 ||
    (code >= 8192 && code <= 8202) ||
    code === 8232 ||
    code === 8233 ||
    code === 8239 ||
    code === 8287 ||
    code === 12288 ||
    code === 65279
  )
}

export function pathMatchesFileNameFilterTokens(
  relativePath: string,
  tokens: readonly string[],
): boolean {
  if (tokens.length === 0) {
    return true
  }
  // Why: locale-independent so host and renderer agree; callers pass already-normalized paths.
  const haystack = relativePath.toLowerCase()
  return tokens.every((token) => haystack.includes(token))
}

/** Filters already-authorized loaded metadata, never Runtime request identity. */
export function filterChangedPaths<
  T extends { path: string; previous_path?: string | null },
>(files: readonly T[], tokens: readonly string[]): T[] {
  if (tokens.length === 0) return [...files]
  return files.filter(
    (file) =>
      pathMatchesFileNameFilterTokens(file.path, tokens) ||
      (file.previous_path != null &&
        pathMatchesFileNameFilterTokens(file.previous_path, tokens)),
  )
}
