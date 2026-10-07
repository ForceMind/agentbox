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
  readonly 'changes.metadataHeading': NoMessageParameters
  readonly 'changes.metadataAvailable': NoMessageParameters
  readonly 'changes.readOnly': NoMessageParameters
  readonly 'changes.readPatch': NoMessageParameters
  readonly 'changes.readPatchLabel': Readonly<{ path: string }>
  readonly 'changes.folderLabel': Readonly<{ path: string }>
  readonly 'changes.readerHeading': NoMessageParameters
  readonly 'changes.readerWarning': NoMessageParameters
  readonly 'changes.readerEmpty': NoMessageParameters
  readonly 'changes.readerLoading': NoMessageParameters
  readonly 'changes.readerUnavailable': NoMessageParameters
  readonly 'changes.readerStale': NoMessageParameters
  readonly 'changes.readerTooLarge': NoMessageParameters
  readonly 'changes.readerBinary': NoMessageParameters
  readonly 'changes.readerPermission': NoMessageParameters
  readonly 'changes.readerFailed': NoMessageParameters
  readonly 'changes.readerCompleted': NoMessageParameters
  readonly 'changes.readerCancel': NoMessageParameters
  readonly 'changes.readerClear': NoMessageParameters
  readonly 'changes.readerCompletedTime': Readonly<{ time: string }>
  readonly 'changes.patchControls': NoMessageParameters
  readonly 'changes.patchUnified': NoMessageParameters
  readonly 'changes.patchRaw': NoMessageParameters
  readonly 'changes.patchWrap': NoMessageParameters
  readonly 'changes.patchLimitFallback': NoMessageParameters
  readonly 'changes.patchFormatFallback': NoMessageParameters
  readonly 'changes.patchCoordinates': NoMessageParameters
  readonly 'changes.patchUnifiedRegion': NoMessageParameters
  readonly 'changes.patchRawRegion': NoMessageParameters
  readonly 'changes.patchCaption': NoMessageParameters
  readonly 'changes.patchOldLine': NoMessageParameters
  readonly 'changes.patchNewLine': NoMessageParameters
  readonly 'changes.patchText': NoMessageParameters
  readonly 'changes.patchContext': NoMessageParameters
  readonly 'changes.patchAdded': NoMessageParameters
  readonly 'changes.patchDeleted': NoMessageParameters
  readonly 'changes.patchMarker': NoMessageParameters
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
        'Paths and status only. Staged patch reading is unavailable without an independent A3 connection and trusted credentials.',
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
      'changes.metadataHeading': () => 'Path metadata',
      'changes.metadataAvailable': () =>
        'Paths and status come from metadata observations. Reading a staged patch requires an explicit action.',
      'changes.readOnly': () => 'Read-only',
      'changes.readPatch': () => 'Read staged patch',
      'changes.readPatchLabel': ({ path }) => `Read staged patch: ${path}`,
      'changes.folderLabel': ({ path }) => `Folder: ${path}`,
      'changes.readerHeading': () => 'Staged patch (read-only)',
      'changes.readerWarning': () =>
        'Source code may contain sensitive information. Reading starts only after an explicit click and supports staged content only. Reads and retries are never automatic.',
      'changes.readerEmpty': () =>
        'No content has been read. Explicitly select a staged added, modified or deleted file.',
      'changes.readerLoading': () =>
        'Verifying identity and reading the complete staged patch. You can cancel at any time.',
      'changes.readerUnavailable': () =>
        'Staged content is unavailable. An independent A3 content connection and trusted credentials are required. Paths and status remain available.',
      'changes.readerStale': () =>
        'This read is no longer current and its content has been cleared. Refresh the page and select a file again.',
      'changes.readerTooLarge': () =>
        'The patch exceeds the complete-read limit. No partial content is shown. Select a smaller staged change.',
      'changes.readerBinary': () =>
        'This is a binary file. Text patches are not supported for it. Select a text file.',
      'changes.readerPermission': () =>
        'Read permission or trusted credentials are no longer valid. Content has been cleared. Reload the page and verify access before trying again.',
      'changes.readerFailed': () =>
        'Integrity verification or the connection failed. Content has been cleared. Refresh and select a file again.',
      'changes.readerCompleted': () =>
        'The complete staged patch has been verified. It is displayed as text only and cleared when it expires or you leave the page.',
      'changes.readerCancel': () => 'Cancel read',
      'changes.readerClear': () => 'Clear content',
      'changes.readerCompletedTime': ({ time }) =>
        `Browser read completed: ${time} (not repository observation time)`,
      'changes.patchControls': () => 'Patch display',
      'changes.patchUnified': () => 'Unified view',
      'changes.patchRaw': () => 'Raw text',
      'changes.patchWrap': () => 'Wrap lines',
      'changes.patchLimitFallback': () =>
        'This patch exceeds the unified view display limits. The complete original text is shown without truncation.',
      'changes.patchFormatFallback': () =>
        'This patch format is not supported by the unified view. The complete original text is shown without truncation.',
      'changes.patchCoordinates': () =>
        'Line numbers are old/new coordinates declared by the patch. Headers do not prove repository or source file identity.',
      'changes.patchUnifiedRegion': () => 'Complete staged patch: unified view',
      'changes.patchRawRegion': () => 'Complete staged patch: raw text',
      'changes.patchCaption': () =>
        'Staged patch lines: + added, − deleted, space for context',
      'changes.patchOldLine': () => 'Old line',
      'changes.patchNewLine': () => 'New line',
      'changes.patchText': () => 'Patch text',
      'changes.patchContext': () => 'Context: ',
      'changes.patchAdded': () => 'Added: ',
      'changes.patchDeleted': () => 'Deleted: ',
      'changes.patchMarker': () => 'Line ending note: ',
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
        '这里只显示路径和状态。缺少独立 A3 内容连接和可信凭据时，暂存补丁读取不可用。',
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
      'changes.metadataHeading': () => '路径与状态',
      'changes.metadataAvailable': () =>
        '路径与状态来自元数据观察。暂存补丁需要单独明确读取。',
      'changes.readOnly': () => '只读',
      'changes.readPatch': () => '读取暂存补丁',
      'changes.readPatchLabel': ({ path }) => `读取暂存补丁：${path}`,
      'changes.folderLabel': ({ path }) => `文件夹: ${path}`,
      'changes.readerHeading': () => '暂存补丁（只读）',
      'changes.readerWarning': () =>
        '源码可能含敏感信息。仅在明确点击后读取，不支持未暂存内容；不会自动读取或重试。',
      'changes.readerEmpty': () =>
        '尚未读取内容。请明确选择一个已暂存的新增、修改或删除文件。',
      'changes.readerLoading': () =>
        '正在验证身份并读取完整暂存补丁，可随时取消。',
      'changes.readerUnavailable': () =>
        '暂存内容暂不可用。需要独立 A3 内容连接和可信凭据；仍可查看路径与状态。',
      'changes.readerStale': () =>
        '此次读取已失效，内容已清除。请刷新页面后重新选择文件。',
      'changes.readerTooLarge': () =>
        '补丁超出完整读取上限，未显示任何片段。请选择较小的暂存变更。',
      'changes.readerBinary': () =>
        '这是二进制文件，暂不支持文本补丁。请选择文本文件。',
      'changes.readerPermission': () =>
        '读取权限或可信凭据已失效，内容已清除。请重新加载页面并验证访问权限后再试。',
      'changes.readerFailed': () =>
        '完整性验证或连接失败，内容已清除。请刷新后重新选择文件。',
      'changes.readerCompleted': () =>
        '完整暂存补丁已验证。内容仅作文本显示，到期或离开页面后清除。',
      'changes.readerCancel': () => '取消读取',
      'changes.readerClear': () => '清除内容',
      'changes.readerCompletedTime': ({ time }) =>
        `浏览器读取完成时间：${time}（非仓库观察时间）`,
      'changes.patchControls': () => '补丁显示方式',
      'changes.patchUnified': () => '统一视图',
      'changes.patchRaw': () => '原文',
      'changes.patchWrap': () => '换行显示',
      'changes.patchLimitFallback': () =>
        '超出统一视图的显示范围，已显示完整原文，未截断。',
      'changes.patchFormatFallback': () =>
        '此补丁格式不支持统一视图，已显示完整原文，未截断。',
      'changes.patchCoordinates': () =>
        '行号仅为补丁声明的旧/新坐标；头部信息不证明仓库或源文件身份。',
      'changes.patchUnifiedRegion': () => '完整暂存补丁：统一视图',
      'changes.patchRawRegion': () => '完整暂存补丁：原文',
      'changes.patchCaption': () => '暂存补丁行：＋增加，−删除，空格为上下文',
      'changes.patchOldLine': () => '旧行',
      'changes.patchNewLine': () => '新行',
      'changes.patchText': () => '补丁文本',
      'changes.patchContext': () => '上下文： ',
      'changes.patchAdded': () => '增加： ',
      'changes.patchDeleted': () => '删除： ',
      'changes.patchMarker': () => '行尾说明： ',
    },
  },
)
