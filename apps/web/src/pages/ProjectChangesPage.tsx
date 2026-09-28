import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
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

export function ProjectChangesPage({
  locale = currentLocale(),
}: {
  locale?: Locale
}) {
  const { projectId } = useParams<{ projectId: string }>()
  const changes = useGitChanges(projectId)
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
            onClick={() => void changes.refresh()}
            type="button"
          >
            <RefreshCw aria-hidden="true" size={16} />{' '}
            {formatMessage(locale, 'changes.refresh', {})}
          </button>
        }
      />
      <p className="interaction-notice changes-metadata-note">
        {formatMessage(locale, 'changes.metadataOnly', {})}
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
              onClick={() => void changes.loadMore()}
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
    </>
  )
}
