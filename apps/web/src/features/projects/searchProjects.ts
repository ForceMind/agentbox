// Adapted from getpaseo/paseo packages/protocol/src/search/text-match.ts
// and packages/app/src/command-center/workspace-search.ts at
// 30178c4f58b67f8472901356e1484022bd835de0 (Apache-2.0).
// Copyright (c) 2025-present Mohamed Boudra. AgentBox searches only
// already-authorized, visible Project metadata and performs no command action.

import type { ProjectData } from '../../lib/contracts'
import { technicalValue } from '../../i18n/technical'

type Match = Readonly<{ tier: number; offset: number; field: number }>

function subsequence(token: string, text: string): number | null {
  const query = [...token]
  for (const match of text.matchAll(/\S+/gu)) {
    const word = match[0]
    let tokenIndex = 0
    for (const character of word) {
      if (character === query[tokenIndex]) tokenIndex += 1
      if (tokenIndex === query.length) return match.index ?? 0
    }
  }
  return null
}

function matchToken(token: string, raw: string, field: number): Match | null {
  if (!raw) return null
  const text = raw.toLowerCase()
  if (text === token) return { tier: 0, offset: 0, field }
  let best: Match | null = null
  let from = 0
  while (from <= text.length - token.length) {
    const offset = text.indexOf(token, from)
    if (offset < 0) break
    const boundary = offset > 0 && !/[\p{L}\p{N}]/u.test(text[offset - 1])
    const tier = offset === 0 ? 1 : boundary ? 2 : 3
    if (
      !best ||
      tier < best.tier ||
      (tier === best.tier && offset < best.offset)
    ) {
      best = { tier, offset, field }
    }
    from = offset + 1
  }
  if (best) return best
  const found = subsequence(token, text)
  return found === null ? null : { tier: 4, offset: found, field }
}

function score(project: ProjectData, tokens: readonly string[]): number | null {
  let branch = ''
  if (project.git?.branch) {
    try {
      branch = technicalValue(project.git.branch).value
    } catch {
      // The Projects page also hides non-printable or non-ASCII branch values.
    }
  }
  const fields = [project.display_name, project.slug, branch]
  let total = 0
  for (const token of tokens) {
    let best: Match | null = null
    for (const [field, value] of fields.entries()) {
      const found = matchToken(token, value, field)
      if (
        found &&
        (!best ||
          found.tier < best.tier ||
          (found.tier === best.tier && found.field < best.field) ||
          (found.tier === best.tier &&
            found.field === best.field &&
            found.offset < best.offset))
      ) {
        best = found
      }
    }
    if (!best) return null
    total += best.tier * 10_000 + best.field * 1000 + Math.min(best.offset, 999)
  }
  return total
}

/** Keep empty-query API order; searched results use stable visible-field rank. */
export function searchProjects(
  projects: readonly ProjectData[],
  query: string,
): ProjectData[] {
  const tokens = query.trim().toLowerCase().split(/\s+/u).filter(Boolean)
  if (tokens.length === 0) return [...projects]
  const matches: Array<{ project: ProjectData; rank: number; index: number }> =
    []
  for (const [index, project] of projects.entries()) {
    const rank = score(project, tokens)
    if (rank !== null) matches.push({ project, rank, index })
  }
  matches.sort(
    (left, right) => left.rank - right.rank || left.index - right.index,
  )
  return matches.map(({ project }) => project)
}
