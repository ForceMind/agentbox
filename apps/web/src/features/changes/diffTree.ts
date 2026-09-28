// Adapted from getpaseo/paseo packages/app/src/git/diff-tree.ts at
// 30178c4f58b67f8472901356e1484022bd835de0 (Apache-2.0).
// Copyright (c) 2025-present Mohamed Boudra. Changed: use AgentBox's
// minimal typed diff summary and preserve richer caller-owned file types.

export interface PathSummary {
  path: string
}

export interface DiffFileSummary extends PathSummary {
  additions: number
  deletions: number
}

// Builds a directory hierarchy from typed summaries for the future AgentBox
// Changes view. The file paths are display data; Runtime path authorization
// belongs to the later Project-scoped content API.
//
// `sortTree` below is the single ordering authority for the Changes view. The
// flat scrolling diff does not sort for itself — `orderCheckoutDiffFiles`
// (diffOrder.ts) builds this tree and reads its file sequence back out — so
// changing `sortTree` reorders both surfaces together, by construction.
//
// Directory nodes are keyed by their FULL uncompressed path (e.g. "packages/app/src").
// That path is the stable identity used to persist folder-collapse state, so the
// state survives path-compression changes as the diff mutates: if a compressed
// row later splits because a sibling appears, the logical directories keep the
// same keys.

export interface DiffTreeFileNode<T extends PathSummary = DiffFileSummary> {
  kind: 'file'
  file: T
  fileIndex: number
  /** basename, e.g. "diff-pane.tsx" */
  name: string
}

export interface DiffTreeDirNode<T extends PathSummary = DiffFileSummary> {
  kind: 'dir'
  /** full uncompressed directory path, e.g. "packages/app/src"; "" for the virtual root */
  dirPath: string
  /** display label; a compressed chain joins segments, e.g. "packages/app/src" */
  name: string
  children: DiffTreeNode<T>[]
}

export type DiffTreeNode<T extends PathSummary = DiffFileSummary> =
  DiffTreeFileNode<T> | DiffTreeDirNode<T>

export interface DiffTreeFolderRow {
  kind: 'folder'
  /** full uncompressed path of the DEEPEST directory this row represents */
  dirPath: string
  /** compressed display label, e.g. "packages/app/src" */
  displayName: string
  depth: number
  additions: number
  deletions: number
}

export interface DiffTreeFileRow<T extends PathSummary = DiffFileSummary> {
  kind: 'file'
  file: T
  fileIndex: number
  depth: number
}

export type DiffTreeRow<T extends DiffFileSummary = DiffFileSummary> =
  DiffTreeFolderRow | DiffTreeFileRow<T>

export type PathTreeRow<T extends PathSummary = PathSummary> =
  | Pick<DiffTreeFolderRow, 'kind' | 'dirPath' | 'displayName' | 'depth'>
  | DiffTreeFileRow<T>

function sortTree<T extends PathSummary>(node: DiffTreeDirNode<T>): void {
  node.children.sort((a, b) => {
    if (a.kind !== b.kind) {
      // directories before files within a level
      return a.kind === 'dir' ? -1 : 1
    }
    // Plain ASCII, not localeCompare: the order must not shift with the
    // device locale, and every surface derives from this comparison.
    if (a.name === b.name) return 0
    return a.name < b.name ? -1 : 1
  })
  for (const child of node.children) {
    if (child.kind === 'dir') {
      sortTree(child)
    }
  }
}

/** Build the (uncompressed) directory tree. Returns the virtual root (dirPath ""). */
export function buildDiffTree<T extends PathSummary>(
  files: readonly T[],
): DiffTreeDirNode<T> {
  const root: DiffTreeDirNode<T> = {
    kind: 'dir',
    dirPath: '',
    name: '',
    children: [],
  }
  const dirByPath = new Map<string, DiffTreeDirNode<T>>([['', root]])

  function ensureDir(dirPath: string): DiffTreeDirNode<T> {
    const existing = dirByPath.get(dirPath)
    if (existing) {
      return existing
    }
    const parts = dirPath.split('/')
    const name = parts[parts.length - 1]
    const parentPath = parts.slice(0, -1).join('/')
    const parent = ensureDir(parentPath)
    const node: DiffTreeDirNode<T> = {
      kind: 'dir',
      dirPath,
      name,
      children: [],
    }
    parent.children.push(node)
    dirByPath.set(dirPath, node)
    return node
  }

  for (const [fileIndex, file] of files.entries()) {
    const parts = file.path.split('/')
    const name = parts[parts.length - 1]
    const dirPath = parts.slice(0, -1).join('/')
    ensureDir(dirPath).children.push({ kind: 'file', file, fileIndex, name })
  }

  sortTree(root)
  return root
}

// Collapse runs of single-child directories into one row, like VS Code / GitHub:
// a directory whose only child is another directory absorbs it. The merged row
// displays the joined segments ("packages/app/src") but keeps the DEEPEST
// directory's full path as its identity.
function compressNode<T extends PathSummary>(
  node: DiffTreeDirNode<T>,
): DiffTreeDirNode<T> {
  let name = node.name
  let dirPath = node.dirPath
  let children = node.children.map((child) =>
    child.kind === 'dir' ? compressNode(child) : child,
  )
  while (children.length === 1 && children[0].kind === 'dir') {
    const only = children[0]
    name = name ? `${name}/${only.name}` : only.name
    dirPath = only.dirPath
    children = only.children
  }
  return { kind: 'dir', dirPath, name, children }
}

/**
 * Compress single-child directory chains. The virtual root is never merged
 * (it isn't rendered); only its subtrees are compressed.
 */
export function compressSingleChildChains<T extends PathSummary>(
  root: DiffTreeDirNode<T>,
): DiffTreeDirNode<T> {
  return {
    ...root,
    children: root.children.map((child) =>
      child.kind === 'dir' ? compressNode(child) : child,
    ),
  }
}

interface DirStats {
  additions: number
  deletions: number
}

const EMPTY_DIR_STATS: DirStats = { additions: 0, deletions: 0 }

// Single post-order pass computing every directory node's aggregate stats from
// its already-summed children — O(n), vs. re-walking each subtree per folder row.
function computeDirStats<T extends DiffFileSummary>(
  root: DiffTreeDirNode<T>,
): Map<DiffTreeDirNode<T>, DirStats> {
  const statsByNode = new Map<DiffTreeDirNode<T>, DirStats>()
  function visit(node: DiffTreeDirNode<T>): DirStats {
    const stats: DirStats = { additions: 0, deletions: 0 }
    for (const child of node.children) {
      if (child.kind === 'file') {
        stats.additions += child.file.additions
        stats.deletions += child.file.deletions
      } else {
        const childStats = visit(child)
        stats.additions += childStats.additions
        stats.deletions += childStats.deletions
      }
    }
    statsByNode.set(node, stats)
    return stats
  }
  visit(root)
  return statsByNode
}

/**
 * Flatten the (compressed) tree into depth-tagged rows for the list. Descendants
 * of any directory whose `dirPath` is in `collapsed` are omitted; folder rows
 * always carry the FULL aggregate stats of their subtree, collapsed or not.
 */
export function flattenDiffTree<T extends DiffFileSummary>(
  root: DiffTreeDirNode<T>,
  collapsed: ReadonlySet<string>,
): DiffTreeRow<T>[] {
  const statsByNode = computeDirStats(root)
  const rows: DiffTreeRow<T>[] = []

  function walk(node: DiffTreeDirNode<T>, depth: number): void {
    for (const child of node.children) {
      if (child.kind === 'file') {
        rows.push({
          kind: 'file',
          file: child.file,
          fileIndex: child.fileIndex,
          depth,
        })
        continue
      }
      const stats = statsByNode.get(child) ?? EMPTY_DIR_STATS
      rows.push({
        kind: 'folder',
        dirPath: child.dirPath,
        displayName: child.name,
        depth,
        additions: stats.additions,
        deletions: stats.deletions,
      })
      if (!collapsed.has(child.dirPath)) {
        walk(child, depth + 1)
      }
    }
  }

  walk(root, 0)
  return rows
}

/** Flatten the same sorted tree for metadata-only paths, without line totals. */
export function flattenPathTree<T extends PathSummary>(
  root: DiffTreeDirNode<T>,
  collapsed: ReadonlySet<string>,
): PathTreeRow<T>[] {
  const rows: PathTreeRow<T>[] = []
  function walk(node: DiffTreeDirNode<T>, depth: number): void {
    for (const child of node.children) {
      if (child.kind === 'file') {
        rows.push({
          kind: 'file',
          file: child.file,
          fileIndex: child.fileIndex,
          depth,
        })
      } else {
        rows.push({
          kind: 'folder',
          dirPath: child.dirPath,
          displayName: child.name,
          depth,
        })
        if (!collapsed.has(child.dirPath)) walk(child, depth + 1)
      }
    }
  }
  walk(root, 0)
  return rows
}

/** Every directory path in the (compressed) tree — used for "collapse all folders". */
export function collectDirPaths<T extends PathSummary>(
  root: DiffTreeDirNode<T>,
): string[] {
  const paths: string[] = []
  function walk(node: DiffTreeDirNode<T>): void {
    for (const child of node.children) {
      if (child.kind === 'dir') {
        paths.push(child.dirPath)
        walk(child)
      }
    }
  }
  walk(root)
  return paths
}
