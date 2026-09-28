import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface ChangesMessageParameters {
  readonly 'changes.title': NoMessageParameters
  readonly 'changes.eyebrow': NoMessageParameters
  readonly 'changes.description': NoMessageParameters
  readonly 'changes.back': NoMessageParameters
  readonly 'changes.refresh': NoMessageParameters
  readonly 'changes.loading': NoMessageParameters
  readonly 'changes.stale': NoMessageParameters
  readonly 'changes.failed': NoMessageParameters
  readonly 'changes.empty': NoMessageParameters
  readonly 'changes.notRepository': NoMessageParameters
  readonly 'changes.showing': Readonly<{ shown: string; total: string }>
  readonly 'changes.loadMore': NoMessageParameters
  readonly 'changes.loadingMore': NoMessageParameters
  readonly 'changes.metadataOnly': NoMessageParameters
  readonly 'changes.folder': NoMessageParameters
  readonly 'changes.was': NoMessageParameters
  readonly 'changes.staged': NoMessageParameters
  readonly 'changes.unstaged': NoMessageParameters
  readonly 'changes.kindAdded': NoMessageParameters
  readonly 'changes.kindModified': NoMessageParameters
  readonly 'changes.kindDeleted': NoMessageParameters
  readonly 'changes.kindRenamed': NoMessageParameters
  readonly 'changes.kindCopied': NoMessageParameters
  readonly 'changes.kindUntracked': NoMessageParameters
  readonly 'changes.kindConflicted': NoMessageParameters
  readonly 'changes.kindTypechanged': NoMessageParameters
}

export const changesCatalog = defineCatalogShard<ChangesMessageParameters>(
  'changes',
  {
    en: {
      'changes.title': () => 'Changed paths',
      'changes.eyebrow': () => 'Project Git',
      'changes.description': () =>
        'A live, read-only tree of Git path and status metadata for this Project.',
      'changes.back': () => 'Back to Project',
      'changes.refresh': () => 'Refresh',
      'changes.loading': () => 'Checking Git changes…',
      'changes.stale': () =>
        'Changes are out of date. Return to this tab or refresh.',
      'changes.failed': () => 'Git changes could not be loaded.',
      'changes.empty': () => 'No changed paths in this repository.',
      'changes.notRepository': () => 'This Project is not a Git repository.',
      'changes.showing': ({ shown, total }) =>
        `Showing ${shown} of ${total} paths`,
      'changes.loadMore': () => 'Load more paths',
      'changes.loadingMore': () => 'Loading more…',
      'changes.metadataOnly': () =>
        'Paths and status only. File content, diff hunks and review actions are not available here yet.',
      'changes.folder': () => 'Folder',
      'changes.was': () => 'from',
      'changes.staged': () => 'Staged',
      'changes.unstaged': () => 'Unstaged',
      'changes.kindAdded': () => 'Added',
      'changes.kindModified': () => 'Modified',
      'changes.kindDeleted': () => 'Deleted',
      'changes.kindRenamed': () => 'Renamed',
      'changes.kindCopied': () => 'Copied',
      'changes.kindUntracked': () => 'Untracked',
      'changes.kindConflicted': () => 'Conflicted',
      'changes.kindTypechanged': () => 'Type changed',
    },
    'zh-CN': {
      'changes.title': () => '变更路径',
      'changes.eyebrow': () => 'Project Git',
      'changes.description': () => '此 Project 的实时只读 Git 路径与状态树。',
      'changes.back': () => '返回 Project',
      'changes.refresh': () => '刷新',
      'changes.loading': () => '正在检查 Git 变更…',
      'changes.stale': () => '变更状态已过期。返回此页面或手动刷新。',
      'changes.failed': () => '无法加载 Git 变更。',
      'changes.empty': () => '此仓库没有变更路径。',
      'changes.notRepository': () => '此 Project 不是 Git 仓库。',
      'changes.showing': ({ shown, total }) =>
        `已显示 ${shown} / ${total} 条路径`,
      'changes.loadMore': () => '加载更多路径',
      'changes.loadingMore': () => '正在加载…',
      'changes.metadataOnly': () =>
        '这里只显示路径和状态，尚不提供文件正文、diff 片段或审查操作。',
      'changes.folder': () => '文件夹',
      'changes.was': () => '原路径',
      'changes.staged': () => '已暂存',
      'changes.unstaged': () => '未暂存',
      'changes.kindAdded': () => '新增',
      'changes.kindModified': () => '修改',
      'changes.kindDeleted': () => '删除',
      'changes.kindRenamed': () => '重命名',
      'changes.kindCopied': () => '复制',
      'changes.kindUntracked': () => '未跟踪',
      'changes.kindConflicted': () => '冲突',
      'changes.kindTypechanged': () => '类型变化',
    },
  },
)
