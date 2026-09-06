import type { Locale } from './locale'

/**
 * Domains are product-facing rather than implementation-facing. A page may add
 * a key in its own domain, but it must add it to both catalogs.
 */
export const MESSAGE_DOMAINS = [
  'app',
  'common',
  'items',
  'document',
  'error',
  'shell',
  'auth',
  'dashboard',
  'codex',
  'claude',
  'workspace',
  'projects',
  'project',
  'doctor',
  'logs',
  'settings',
  'notFound',
] as const

export type MessageDomain = (typeof MESSAGE_DOMAINS)[number]

export const MESSAGE_KEYS = [
  'app.name',
  'common.cancel',
  'common.close',
  'common.loading',
  'common.retry',
  'common.unknown',
  'document.title',
  'items.count',
  'error.unknown',
  'error.controlPlaneUnavailable',
  'error.requestTimeout',
  'error.codexStatusUnavailable',
  'error.codexActionFailed',
  'error.codexPairFailed',
  'error.claudeActionFailed',
  'error.doctorUnavailable',
  'error.projectIdentityChanged',
  'error.projectNotReady',
  'error.reconciliationRequired',
  'error.wawActionBusy',
  'error.wawActionFailed',
  'error.wawActionStale',
  'error.wawInvalidAgent',
  'error.wawMetadataInvalid',
  'error.wawSessionRequired',
  'error.wawStatusUnavailable',
  'error.workspaceNotFound',
  'shell.dashboard',
  'shell.codex',
  'shell.claude',
  'shell.workspace',
  'shell.projects',
  'shell.doctor',
  'shell.logs',
  'shell.settings',
  'auth.title',
  'dashboard.title',
  'codex.title',
  'claude.title',
  'workspace.title',
  'projects.title',
  'project.title',
  'doctor.title',
  'logs.title',
  'settings.title',
  'notFound.title',
] as const

export type MessageKey = (typeof MESSAGE_KEYS)[number]

type EmptyMessageParameters = Readonly<Record<never, never>>

export type MessageParameters = Readonly<{
  [
    Key in Exclude<MessageKey, 'document.title' | 'items.count'>
  ]: EmptyMessageParameters
}> & {
  readonly 'document.title': Readonly<{ title: string }>
  readonly 'items.count': Readonly<{ count: string }>
}

export type MessageCatalog = Readonly<{
  [Key in MessageKey]: (parameters: MessageParameters[Key]) => string
}>

function defineCatalog(catalog: MessageCatalog): MessageCatalog {
  return Object.freeze(catalog)
}

const en = defineCatalog({
  'app.name': () => 'AgentBox',
  'common.cancel': () => 'Cancel',
  'common.close': () => 'Close',
  'common.loading': () => 'Loading…',
  'common.retry': () => 'Retry',
  'common.unknown': () => 'Unknown',
  'document.title': ({ title }: MessageParameters['document.title']) =>
    `${title} · AgentBox`,
  'items.count': ({ count }: MessageParameters['items.count']) =>
    `${count} items`,
  'error.unknown': () => 'The operation could not be completed. Try again.',
  'error.controlPlaneUnavailable': () => 'The control plane is unavailable.',
  'error.requestTimeout': () => 'The request timed out. Try again.',
  'error.codexStatusUnavailable': () =>
    'Codex status is temporarily unavailable.',
  'error.codexActionFailed': () =>
    'The Codex operation could not be completed.',
  'error.codexPairFailed': () => 'A Codex pair code could not be created.',
  'error.claudeActionFailed': () =>
    'The Claude operation could not be completed.',
  'error.doctorUnavailable': () => 'Diagnostics are temporarily unavailable.',
  'error.projectIdentityChanged': () =>
    'The Project or Runtime identity changed. Refresh and try again.',
  'error.projectNotReady': () =>
    'This Project is not ready for the requested operation.',
  'error.reconciliationRequired': () =>
    'Runtime reconciliation is required before continuing.',
  'error.wawActionBusy': () => 'A workspace operation is already in progress.',
  'error.wawActionFailed': () =>
    'The workspace operation could not be completed.',
  'error.wawActionStale': () =>
    'The workspace state changed. Refresh and try again.',
  'error.wawInvalidAgent': () => 'The selected AgentType is not valid.',
  'error.wawMetadataInvalid': () =>
    'Workspace information is incomplete. Refresh and try again.',
  'error.wawSessionRequired': () => 'Sign in again before using the workspace.',
  'error.wawStatusUnavailable': () =>
    'Workspace status is temporarily unavailable.',
  'error.workspaceNotFound': () => 'The requested workspace was not found.',
  'shell.dashboard': () => 'Dashboard',
  'shell.codex': () => 'Codex',
  'shell.claude': () => 'Claude',
  'shell.workspace': () => 'Workspace',
  'shell.projects': () => 'Projects',
  'shell.doctor': () => 'Doctor',
  'shell.logs': () => 'Logs',
  'shell.settings': () => 'Settings',
  'auth.title': () => 'Sign in',
  'dashboard.title': () => 'Dashboard',
  'codex.title': () => 'Codex',
  'claude.title': () => 'Claude',
  'workspace.title': () => 'Interactive workspace',
  'projects.title': () => 'Projects',
  'project.title': () => 'Project',
  'doctor.title': () => 'Doctor',
  'logs.title': () => 'Logs',
  'settings.title': () => 'Settings',
  'notFound.title': () => 'Page not found',
})

const zhCN = defineCatalog({
  'app.name': () => 'AgentBox',
  'common.cancel': () => '取消',
  'common.close': () => '关闭',
  'common.loading': () => '正在加载…',
  'common.retry': () => '重试',
  'common.unknown': () => '未知',
  'document.title': ({ title }: MessageParameters['document.title']) =>
    `${title} · AgentBox`,
  'items.count': ({ count }: MessageParameters['items.count']) => `${count} 项`,
  'error.unknown': () => '操作未完成，请重试。',
  'error.controlPlaneUnavailable': () => '控制平面暂不可用。',
  'error.requestTimeout': () => '请求超时，请重试。',
  'error.codexStatusUnavailable': () => 'Codex 状态暂不可用。',
  'error.codexActionFailed': () => 'Codex 操作未完成。',
  'error.codexPairFailed': () => '无法创建 Codex 配对码。',
  'error.claudeActionFailed': () => 'Claude 操作未完成。',
  'error.doctorUnavailable': () => '诊断信息暂不可用。',
  'error.projectIdentityChanged': () =>
    'Project 或 Runtime 身份已变化，请刷新后重试。',
  'error.projectNotReady': () => '该 Project 尚未准备好执行此操作。',
  'error.reconciliationRequired': () => '继续前需要完成 Runtime 恢复核对。',
  'error.wawActionBusy': () => '已有工作区操作正在进行。',
  'error.wawActionFailed': () => '工作区操作未完成。',
  'error.wawActionStale': () => '工作区状态已变化，请刷新后重试。',
  'error.wawInvalidAgent': () => '所选 AgentType 无效。',
  'error.wawMetadataInvalid': () => '工作区信息不完整，请刷新后重试。',
  'error.wawSessionRequired': () => '请重新登录后再使用工作区。',
  'error.wawStatusUnavailable': () => '工作区状态暂不可用。',
  'error.workspaceNotFound': () => '未找到请求的工作区。',
  'shell.dashboard': () => '概览',
  'shell.codex': () => 'Codex',
  'shell.claude': () => 'Claude',
  'shell.workspace': () => '工作区',
  'shell.projects': () => '项目',
  'shell.doctor': () => '诊断',
  'shell.logs': () => '日志',
  'shell.settings': () => '设置',
  'auth.title': () => '登录',
  'dashboard.title': () => '概览',
  'codex.title': () => 'Codex',
  'claude.title': () => 'Claude',
  'workspace.title': () => '交互式工作区',
  'projects.title': () => '项目',
  'project.title': () => 'Project',
  'doctor.title': () => '诊断',
  'logs.title': () => '日志',
  'settings.title': () => '设置',
  'notFound.title': () => '未找到页面',
})

export const messageCatalogs: Readonly<Record<Locale, MessageCatalog>> =
  Object.freeze({
    en,
    'zh-CN': zhCN,
  })

export class I18nMessageError extends Error {
  constructor(readonly key: string) {
    super(`Missing i18n message: ${key}`)
    this.name = 'I18nMessageError'
  }
}

/** Formats an explicitly typed message; message keys never fall back to source text. */
export function formatMessage<Key extends MessageKey>(
  locale: Locale,
  key: Key,
  parameters: MessageParameters[Key],
): string {
  const formatter = messageCatalogs[locale][key]
  if (typeof formatter !== 'function') throw new I18nMessageError(key)
  return formatter(parameters)
}

export function messageDomain(key: MessageKey): MessageDomain {
  const domain = key.split('.', 1)[0]
  if ((MESSAGE_DOMAINS as readonly string[]).includes(domain))
    return domain as MessageDomain
  throw new I18nMessageError(key)
}
