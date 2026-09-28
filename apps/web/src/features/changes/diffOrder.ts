// Adapted from getpaseo/paseo packages/app/src/git/diff-order.ts at
// 30178c4f58b67f8472901356e1484022bd835de0 (Apache-2.0).
// Copyright (c) 2025-present Mohamed Boudra. Changed: AgentBox-local types.
import {
  buildDiffTree,
  flattenDiffTree,
  type DiffFileSummary,
} from './diffTree'

// The Changes tree is the single ordering authority: `sortTree` (diffTree.ts)
// ranks directories before files within a level, then compares names. Surfaces
// that render the flat file list — the scrolling diff — derive their order from
// the tree here instead of reimplementing the rule, so the two cannot disagree.
export function orderCheckoutDiffFiles<T extends DiffFileSummary>(
  files: T[],
): T[] {
  if (files.length < 2) {
    return files
  }
  // Path compression only merges display rows for single-child directory
  // chains, so it is skipped; the collapsed set is empty because the flat list
  // always carries every file, whatever the rail has collapsed.
  return flattenDiffTree(buildDiffTree(files), new Set()).flatMap((row) =>
    row.kind === 'file' ? [row.file] : [],
  )
}
