import { appCatalog } from './catalogs/app'
import type { AppMessageParameters } from './catalogs/app'
import { authCatalog } from './catalogs/auth'
import type { AuthMessageParameters } from './catalogs/auth'
import { claudeCatalog } from './catalogs/claude'
import type { ClaudeMessageParameters } from './catalogs/claude'
import { codexCatalog } from './catalogs/codex'
import type { CodexMessageParameters } from './catalogs/codex'
import { commonCatalog } from './catalogs/common'
import type { CommonMessageParameters } from './catalogs/common'
import { dashboardCatalog } from './catalogs/dashboard'
import type { DashboardMessageParameters } from './catalogs/dashboard'
import { doctorCatalog } from './catalogs/doctor'
import type { DoctorMessageParameters } from './catalogs/doctor'
import { documentCatalog } from './catalogs/document'
import type { DocumentMessageParameters } from './catalogs/document'
import { errorCatalog } from './catalogs/error'
import type { ErrorMessageParameters } from './catalogs/error'
import { itemsCatalog } from './catalogs/items'
import type { ItemsMessageParameters } from './catalogs/items'
import { logsCatalog } from './catalogs/logs'
import type { LogsMessageParameters } from './catalogs/logs'
import { notFoundCatalog } from './catalogs/notFound'
import type { NotFoundMessageParameters } from './catalogs/notFound'
import { projectCatalog } from './catalogs/project'
import type { ProjectMessageParameters } from './catalogs/project'
import { projectsCatalog } from './catalogs/projects'
import type { ProjectsMessageParameters } from './catalogs/projects'
import { settingsCatalog } from './catalogs/settings'
import type { SettingsMessageParameters } from './catalogs/settings'
import { shellCatalog } from './catalogs/shell'
import type { ShellMessageParameters } from './catalogs/shell'
import type { CatalogFor } from './catalogs/types'
import { workspaceCatalog } from './catalogs/workspace'
import type { WorkspaceMessageParameters } from './catalogs/workspace'
import { MESSAGE_DOMAINS, type MessageDomain } from './domains'
import type { Locale } from './locale'

export { MESSAGE_DOMAINS, type MessageDomain } from './domains'

export interface MessageParameters
  extends
    AppMessageParameters,
    CommonMessageParameters,
    ItemsMessageParameters,
    DocumentMessageParameters,
    ErrorMessageParameters,
    ShellMessageParameters,
    AuthMessageParameters,
    DashboardMessageParameters,
    CodexMessageParameters,
    ClaudeMessageParameters,
    WorkspaceMessageParameters,
    ProjectsMessageParameters,
    ProjectMessageParameters,
    DoctorMessageParameters,
    LogsMessageParameters,
    SettingsMessageParameters,
    NotFoundMessageParameters {}

export type MessageKey = Extract<keyof MessageParameters, string>
export type MessageCatalog = CatalogFor<MessageParameters>
export type MessageArguments = {
  [Key in MessageKey]: readonly [key: Key, parameters: MessageParameters[Key]]
}[MessageKey]
export type ParameterFreeMessageKey = {
  [Key in MessageKey]: MessageParameters[Key] extends Readonly<
    Record<string, never>
  >
    ? Key
    : never
}[MessageKey]

const catalogShards = Object.freeze([
  appCatalog,
  commonCatalog,
  itemsCatalog,
  documentCatalog,
  errorCatalog,
  shellCatalog,
  authCatalog,
  dashboardCatalog,
  codexCatalog,
  claudeCatalog,
  workspaceCatalog,
  projectsCatalog,
  projectCatalog,
  doctorCatalog,
  logsCatalog,
  settingsCatalog,
  notFoundCatalog,
])

export class I18nMessageError extends Error {
  constructor(readonly key: string) {
    super(`Missing i18n message: ${key}`)
    this.name = 'I18nMessageError'
  }
}

function composeCatalog(locale: Locale): MessageCatalog {
  const composed: Record<string, unknown> = {}

  for (const shard of catalogShards) {
    for (const [key, formatter] of Object.entries(shard.catalogs[locale])) {
      if (Object.hasOwn(composed, key)) {
        throw new TypeError(`Duplicate i18n message: ${key}`)
      }
      composed[key] = formatter
    }
  }

  return Object.freeze(composed) as MessageCatalog
}

const en = composeCatalog('en')
const zhCN = composeCatalog('zh-CN')

export const messageCatalogs: Readonly<Record<Locale, MessageCatalog>> =
  Object.freeze({
    en,
    'zh-CN': zhCN,
  })

/** Runtime inventory for parity checks and migration tooling. */
export const MESSAGE_KEYS: readonly MessageKey[] = Object.freeze(
  Object.keys(en) as MessageKey[],
)

/** Builds a safe descriptor for any dynamic key whose contract has no values. */
export function parameterFreeMessage(
  key: ParameterFreeMessageKey,
): MessageArguments {
  return [key, {}] as MessageArguments
}

/**
 * Formats a typed message. The distributed tuple keeps a dynamic key paired
 * with only its own parameters instead of widening both to unrelated unions.
 */
export function formatMessage(
  locale: Locale,
  ...arguments_: MessageArguments
): string {
  const [key, parameters] = arguments_
  const formatter = messageCatalogs[locale][key]
  if (typeof formatter !== 'function') throw new I18nMessageError(key)
  return (formatter as (value: unknown) => string)(parameters)
}

export function messageDomain(key: MessageKey): MessageDomain {
  const domain = key.split('.', 1)[0]
  if ((MESSAGE_DOMAINS as readonly string[]).includes(domain)) {
    return domain as MessageDomain
  }
  throw new I18nMessageError(key)
}
