import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  FileDiff,
  FolderTree,
  LockKeyhole,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
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
import { VerifiedPatchView } from '../features/changes/VerifiedPatchView'
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

const READER_COPY = {
  empty: 'changes.readerEmpty',
  loading: 'changes.readerLoading',
  unavailable: 'changes.readerUnavailable',
  stale: 'changes.readerStale',
  'too-large': 'changes.readerTooLarge',
  binary: 'changes.readerBinary',
  permission: 'changes.readerPermission',
  failed: 'changes.readerFailed',
  completed: 'changes.readerCompleted',
} as const satisfies Record<A3ChangesStatus, `changes.${string}`>

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
    <div className="changes-page">
      <Link
        className="back-link secondary-button changes-back"
        to={
          projectId ? `/projects/${encodeURIComponent(projectId)}` : '/projects'
        }
      >
        <ArrowLeft aria-hidden="true" size={16} />
        {formatMessage(locale, 'changes.back', {})}
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
      <div className="changes-workbench">
        <section
          className="runtime-card changes-card"
          aria-labelledby="changes-metadata-heading"
        >
          <div className="changes-section-heading">
            <h2 id="changes-metadata-heading">
              <FolderTree aria-hidden="true" size={19} />
              {formatMessage(locale, 'changes.metadataHeading', {})}
            </h2>
            <span className="status-badge">
              {formatMessage(locale, 'changes.readOnly', {})}
            </span>
          </div>
          <p className="changes-metadata-note">
            {formatMessage(
              locale,
              reader.available
                ? 'changes.metadataAvailable'
                : 'changes.metadataOnly',
              {},
            )}
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
            <p className="changes-metadata-state" role="status">
              {formatMessage(locale, 'changes.stale', {})}
            </p>
          ) : changes.loading ? (
            <p className="changes-metadata-state" role="status">
              {formatMessage(locale, 'changes.loading', {})}
            </p>
          ) : !changes.isRepository ? (
            <p className="changes-metadata-state" role="status">
              {formatMessage(locale, 'changes.notRepository', {})}
            </p>
          ) : changes.files.length === 0 ? (
            <p className="changes-metadata-state" role="status">
              {formatMessage(locale, 'changes.empty', {})}
            </p>
          ) : (
            <>
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
                          aria-label={formatMessage(
                            locale,
                            'changes.folderLabel',
                            { path: label },
                          )}
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
                      data-kind={file.kind}
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
                        ['added', 'modified', 'deleted'].includes(
                          file.kind,
                        ) && (
                          <button
                            className="secondary-button changes-read"
                            type="button"
                            disabled={
                              !reader.available ||
                              changes.loading ||
                              changes.stale
                            }
                            aria-label={formatMessage(
                              locale,
                              'changes.readPatchLabel',
                              { path: visibleGitPath(file.path) },
                            )}
                            aria-controls="a3-changes-reader"
                            onClick={() => void readerController.read(file)}
                          >
                            {formatMessage(locale, 'changes.readPatch', {})}
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
            </>
          )}
        </section>
        <section
          className="runtime-card changes-reader"
          id="a3-changes-reader"
          aria-labelledby="a3-reader-heading"
        >
          <div className="changes-section-heading">
            <h2 id="a3-reader-heading">
              <FileDiff aria-hidden="true" size={19} />
              {formatMessage(locale, 'changes.readerHeading', {})}
            </h2>
            <LockKeyhole aria-hidden="true" size={18} />
          </div>
          <p className="changes-reader-warning">
            <ShieldAlert aria-hidden="true" size={18} />
            <span>{formatMessage(locale, 'changes.readerWarning', {})}</span>
          </p>
          <p
            className="changes-reader-state"
            role="status"
            aria-live="polite"
            data-testid="a3-reader-status"
            data-status={reader.state.status}
          >
            {formatMessage(locale, READER_COPY[reader.state.status], {})}
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
              {formatMessage(
                locale,
                reader.state.status === 'loading'
                  ? 'changes.readerCancel'
                  : 'changes.readerClear',
                {},
              )}
            </button>
          )}
          {reader.state.status === 'completed' &&
            reader.state.text !== null && (
              <>
                <p className="changes-reader-time">
                  {formatMessage(locale, 'changes.readerCompletedTime', {
                    time: new Date(reader.state.completedAtMs!).toLocaleString(
                      locale,
                    ),
                  })}
                </p>
                <VerifiedPatchView text={reader.state.text} locale={locale} />
              </>
            )}
        </section>
      </div>
    </div>
  )
}
