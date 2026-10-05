import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { LocalizedApiError } from '../components/i18n'
import { OpaqueUserValue } from '../components/i18n/OpaqueUserValue'
import { PageHeader } from '../components/PageHeader'
import {
  buildDiffTree,
  compressSingleChildChains,
  flattenPathTree,
} from '../features/changes/diffTree'
import { useGitChanges } from '../features/changes/useGitChanges'
import { visibleGitPath } from '../features/changes/visibleGitPath'
import { useA3ChangesReader } from '../features/content/useA3ChangesReader'
import type { A3ChangesDependencies } from '../features/content/a3ChangesTrust'
import type { A3ChangesStatus } from '../features/content/a3ChangesController'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, formatMessage, type Locale } from '../i18n'
import type { GitChangeKind } from '../lib/contracts'
import './ProjectChangesPage.css'

const KIND_COPY = {
  added: 'changes.kindAdded',
  modified: 'changes.kindModified',
  deleted: 'changes.kindDeleted',
  renamed: 'changes.kindRenamed',
  copied: 'changes.kindCopied',
  untracked: 'changes.kindUntracked',
  conflicted: 'changes.kindConflicted',
  typechanged: 'changes.kindTypechanged',
} as const satisfies Record<GitChangeKind, `changes.${string}`>

const READER_COPY: Record<A3ChangesStatus, string> = {
  empty: '尚未读取内容。请明确选择一个已暂存的新增、修改或删除文件。',
  loading: '正在验证身份并读取完整暂存补丁，可随时取消。',
  unavailable:
    '暂存内容暂不可用。需要独立 A3 内容连接和可信凭据；仍可查看路径与状态。',
  stale: '此次读取已失效，内容已清除。请刷新页面后重新选择文件。',
  'too-large': '补丁超出完整读取上限，未显示任何片段。请选择较小的暂存变更。',
  binary: '这是二进制文件，暂不支持文本补丁。请选择文本文件。',
  permission:
    '读取权限或可信凭据已失效，内容已清除。请重新加载页面并验证访问权限后再试。',
  failed: '完整性验证或连接失败，内容已清除。请刷新后重新选择文件。',
  completed: '完整暂存补丁已验证。内容仅作文本显示，到期或离开页面后清除。',
}

export function ProjectChangesPage({
  locale = currentLocale(),
  a3Dependencies,
}: {
  locale?: Locale
  a3Dependencies?: A3ChangesDependencies
}) {
  const { projectId } = useParams<{ projectId: string }>()
  const changes = useGitChanges(projectId)
  const reader = useA3ChangesReader(projectId, a3Dependencies)
  const readerController = reader.controller
  useLayoutEffect(() => {
    readerController.clear(changes.stale || changes.error ? 'stale' : 'empty')
  }, [
    readerController,
    changes.files,
    changes.loading,
    changes.stale,
    changes.error,
  ])
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set())
  usePageTitle(formatMessage(locale, 'changes.title', {}))

  useEffect(() => setCollapsed(new Set()), [projectId])

  const rows = useMemo(() => {
    return flattenPathTree(
      compressSingleChildChains(buildDiffTree(changes.files)),
      collapsed,
    )
  }, [changes.files, collapsed])

  function toggleFolder(dirPath: string) {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(dirPath)) next.delete(dirPath)
      else next.add(dirPath)
      return next
    })
  }

  return (
    <>
      <Link
        className="back-link secondary-button"
        to={
          projectId ? `/projects/${encodeURIComponent(projectId)}` : '/projects'
        }
      >
        ← {formatMessage(locale, 'changes.back', {})}
      </Link>
      <PageHeader
        eyebrow={formatMessage(locale, 'changes.eyebrow', {})}
        title={formatMessage(locale, 'changes.title', {})}
        description={formatMessage(locale, 'changes.description', {})}
        action={
          <button
            className="secondary-button"
            onClick={() => {
              readerController.clear('stale')
              void changes.refresh()
            }}
            type="button"
          >
            <RefreshCw aria-hidden="true" size={16} />{' '}
            {formatMessage(locale, 'changes.refresh', {})}
          </button>
        }
      />
      <p className="interaction-notice changes-metadata-note">
        {reader.available
          ? '路径与状态来自元数据观察。暂存补丁需要单独明确读取。'
          : formatMessage(locale, 'changes.metadataOnly', {})}
      </p>

      {changes.error ? (
        <section className="error-panel" role="alert">
          <p>{formatMessage(locale, 'changes.failed', {})}</p>
          <LocalizedApiError
            error={changes.error}
            locale={locale}
            role="presentation"
          />
        </section>
      ) : changes.stale ? (
        <p className="runtime-card" role="status">
          {formatMessage(locale, 'changes.stale', {})}
        </p>
      ) : changes.loading ? (
        <p className="runtime-card" role="status">
          {formatMessage(locale, 'changes.loading', {})}
        </p>
      ) : !changes.isRepository ? (
        <p className="runtime-card" role="status">
          {formatMessage(locale, 'changes.notRepository', {})}
        </p>
      ) : changes.files.length === 0 ? (
        <p className="runtime-card" role="status">
          {formatMessage(locale, 'changes.empty', {})}
        </p>
      ) : (
        <section className="runtime-card changes-card">
          <p className="changes-count">
            {formatMessage(locale, 'changes.showing', {
              shown: String(changes.files.length),
              total: String(changes.totalCount),
            })}
          </p>
          <ol className="changes-tree">
            {rows.map((row) => {
              const depth = Math.min(row.depth, 6)
              if (row.kind === 'folder') {
                const label = visibleGitPath(row.displayName)
                const folded = collapsed.has(row.dirPath)
                return (
                  <li
                    className="changes-folder"
                    key={`folder:${row.dirPath}`}
                    style={{ paddingInlineStart: `${depth * 1.1}rem` }}
                  >
                    <button
                      aria-expanded={!folded}
                      aria-label={`${formatMessage(locale, 'changes.folder', {})}: ${label}`}
                      onClick={() => toggleFolder(row.dirPath)}
                      type="button"
                    >
                      {folded ? (
                        <ChevronRight aria-hidden="true" size={16} />
                      ) : (
                        <ChevronDown aria-hidden="true" size={16} />
                      )}
                      <OpaqueUserValue value={label} />
                    </button>
                  </li>
                )
              }
              const file = row.file
              const name = visibleGitPath(
                file.path.split('/').at(-1) ?? file.path,
              )
              return (
                <li
                  className="changes-file"
                  key={`file:${file.path}`}
                  style={{ paddingInlineStart: `${depth * 1.1}rem` }}
                >
                  <span className="changes-file-name">
                    <OpaqueUserValue value={name} />
                  </span>
                  <span className="changes-kind">
                    {formatMessage(locale, KIND_COPY[file.kind], {})}
                  </span>
                  {file.staged && (
                    <span className="changes-stage">
                      {formatMessage(locale, 'changes.staged', {})}
                    </span>
                  )}
                  {file.unstaged && (
                    <span className="changes-stage">
                      {formatMessage(locale, 'changes.unstaged', {})}
                    </span>
                  )}
                  {file.staged &&
                    ['added', 'modified', 'deleted'].includes(file.kind) && (
                      <button
                        className="secondary-button changes-read"
                        type="button"
                        disabled={
                          !reader.available || changes.loading || changes.stale
                        }
                        aria-label={`读取暂存补丁：${visibleGitPath(file.path)}`}
                        aria-controls="a3-changes-reader"
                        onClick={() => void readerController.read(file)}
                      >
                        读取暂存补丁
                      </button>
                    )}
                  {file.previous_path && (
                    <small className="changes-previous">
                      {formatMessage(locale, 'changes.was', {})}{' '}
                      <OpaqueUserValue
                        value={visibleGitPath(file.previous_path)}
                      />
                    </small>
                  )}
                </li>
              )
            })}
          </ol>
          {changes.nextCursor && (
            <button
              className="secondary-button changes-more"
              disabled={changes.loadingMore}
              onClick={() => {
                readerController.clear('stale')
                void changes.loadMore()
              }}
              type="button"
            >
              {formatMessage(
                locale,
                changes.loadingMore
                  ? 'changes.loadingMore'
                  : 'changes.loadMore',
                {},
              )}
            </button>
          )}
        </section>
      )}
      <section
        className="runtime-card changes-reader"
        id="a3-changes-reader"
        aria-labelledby="a3-reader-heading"
      >
        <h2 id="a3-reader-heading">暂存补丁（只读）</h2>
        <p className="interaction-notice">
          源码可能含敏感信息。仅在明确点击后读取，不支持未暂存内容；不会自动读取或重试。
        </p>
        <p role="status" aria-live="polite" data-testid="a3-reader-status">
          {READER_COPY[reader.state.status]}
        </p>
        {reader.state.path && (
          <p className="changes-reader-path">
            <OpaqueUserValue value={visibleGitPath(reader.state.path)} />
          </p>
        )}
        {(reader.state.status === 'loading' ||
          reader.state.status === 'completed') && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => readerController.clear()}
          >
            {reader.state.status === 'loading' ? '取消读取' : '清除内容'}
          </button>
        )}
        {reader.state.status === 'completed' && reader.state.text !== null && (
          <>
            <p className="changes-reader-time">
              浏览器读取完成时间：
              {new Date(reader.state.completedAtMs!).toLocaleString('zh-CN')}
              （非仓库观察时间）
            </p>
            <pre
              className="changes-patch"
              tabIndex={0}
              aria-label="完整暂存补丁"
              data-testid="a3-complete-patch"
            >
              {reader.state.text}
            </pre>
          </>
        )}
      </section>
    </>
  )
}
