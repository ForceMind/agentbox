# R11 rc9 route-state localization manifest

Status: implementation inventory for rc9. It defines page-migration scope; it
does not claim that those pages already use the catalog or that R11 is complete.

## Fixed locale and rendering rules

- The document locale is selected once before React renders from only
  `navigator.languages[0]`. A valid primary language `zh` selects `zh-CN`; every
  other, missing or malformed value selects `en`. `navigator.language` and later
  list values are ignored. Changing browser language requires a reload.
- User-visible prose comes from the typed `apps/web/src/i18n` catalog. English
  and Chinese key sets must remain exact peers at TypeScript build time and in
  the catalog parity test.
- API error display uses `localizeApiError(locale, error.code)`. It must never
  render `ApiError.message` or server prose. Known codes have a localized
  message; unknown codes receive a generic localized failure message.
- Error code and request ID, when valid printable ASCII, use
  `technicalApiIdentifier()` and technical rendering (`lang=en`, `dir=ltr`,
  `translate=no`). Protocol values, enum identifiers, AgentType, Audit actions,
  branches, filenames, repositories, Git/GitHub, tmux, Claude and Codex remain
  English. Project and user names remain user Unicode data.

## Route and state inventory

| Route                     | Owner surface                                         | Required states and dialogs                                                                                                                            | Catalog domains                        |
| ------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| `/`                       | RootRedirect                                          | restoring session; redirect authenticated/anonymous                                                                                                    | `auth`, `common`                       |
| `/login`                  | LoginPage                                             | form, validation, pending, invalid credentials, rate limit, unavailable                                                                                | `auth`, `error`, `common`              |
| `/dashboard`              | DashboardPage                                         | loading, unavailable, healthy/degraded cards                                                                                                           | `dashboard`, `error`, `common`         |
| `/codex`                  | CodexPage                                             | loading, unavailable, status, capability states, Remote start/stop, Pair reveal/copy/error                                                             | `codex`, `error`, `common`             |
| `/claude`                 | ClaudePage                                            | loading, unavailable, installation/session empty, start/stop, sensitive-output reveal/hide/error                                                       | `claude`, `error`, `common`            |
| `/workspace`              | WorkspacePage                                         | Project/AgentType selection, loading/unregistered/error, lifecycle, terminal admission, Connect/reconnect/detach/input/resize, exact Stop confirmation | `workspace`, `error`, `common`         |
| `/workspace/:workspaceId` | WorkspacePage                                         | direct lookup success/not found/identity mismatch/reconciliation plus the workspace states above                                                       | `workspace`, `error`, `common`         |
| `/projects`               | ProjectsPage                                          | loading, empty, create form validation/pending/error, Project cards                                                                                    | `projects`, `error`, `common`          |
| `/projects/:projectId`    | ProjectDetailPage                                     | loading/not found/error, Git status/action errors, branch form, Draft PR form, Claude controls                                                         | `project`, `claude`, `error`, `common` |
| `/doctor`                 | DoctorPage                                            | loading, unavailable, check/capability/authentication states                                                                                           | `doctor`, `error`, `common`            |
| `/logs`                   | LogsPage / PlannedPage                                | planned capability text and empty/planned state                                                                                                        | `logs`, `common`                       |
| `/settings`               | SettingsPage                                          | loading, error, profile/session settings state                                                                                                         | `settings`, `error`, `common`          |
| `*`                       | NotFoundPage                                          | unavailable route and return action                                                                                                                    | `notFound`, `common`                   |
| shell                     | AppShell, navigation, ControlPlanePulse, route guards | desktop/mobile navigation, menu open/close, logout pending/error, health checking/healthy/unavailable                                                  | `shell`, `common`, `error`             |

## Migration and verification sequence

1. Keep locale selection and shared catalog/error mapper as the sole foundation.
   Page owners add keys only to their named domain and remove local `COPY`
   objects or hardcoded user prose in the same page change.
2. Migrate shell/auth first, then Dashboard/Codex/Claude, Projects/detail,
   Doctor/Logs/Settings/NotFound, and finally Workspace together with the real
   controller UI. Do not change technical identifiers into translated labels.
3. For each route, add unit coverage for code-to-message handling and E2E for
   loading, empty where applicable, error, success and dialog state in both
   locales. The final rc9 matrix uses `1280x800` and `390x844`, asserts document
   `lang`, no horizontal overflow and at least 44px interactive controls.
4. Terminal E2E uses non-sensitive fixtures and keeps trace, video and
   screenshots disabled. Browser output, keys, tickets and API server prose are
   not retained in storage, reports or DOM after a fence.
