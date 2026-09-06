import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface ErrorMessageParameters {
  readonly 'error.unknown': NoMessageParameters
  readonly 'error.codeLabel': NoMessageParameters
  readonly 'error.requestIdLabel': NoMessageParameters
  readonly 'error.authCsrfInvalid': NoMessageParameters
  readonly 'error.authInvalidCredentials': NoMessageParameters
  readonly 'error.authRateLimited': NoMessageParameters
  readonly 'error.authRecentRequired': NoMessageParameters
  readonly 'error.authSessionInvalid': NoMessageParameters
  readonly 'error.claudeRuntimeUnavailable': NoMessageParameters
  readonly 'error.codexRemoteStatusUnsupported': NoMessageParameters
  readonly 'error.codexCommandTimeout': NoMessageParameters
  readonly 'error.codexExecutableChanged': NoMessageParameters
  readonly 'error.codexExecutableInvalid': NoMessageParameters
  readonly 'error.codexNotInstalled': NoMessageParameters
  readonly 'error.codexOutputLimitExceeded': NoMessageParameters
  readonly 'error.codexPairOutputUnrecognized': NoMessageParameters
  readonly 'error.codexPairRateLimited': NoMessageParameters
  readonly 'error.codexPairTimeout': NoMessageParameters
  readonly 'error.codexPairUnsupported': NoMessageParameters
  readonly 'error.codexRemoteStartFailed': NoMessageParameters
  readonly 'error.codexRemoteStopFailed': NoMessageParameters
  readonly 'error.codexRemoteUnsupported': NoMessageParameters
  readonly 'error.codexUnauthenticated': NoMessageParameters
  readonly 'error.projectNotFound': NoMessageParameters
  readonly 'error.controlPlaneUnavailable': NoMessageParameters
  readonly 'error.requestTimeout': NoMessageParameters
  readonly 'error.codexStatusUnavailable': NoMessageParameters
  readonly 'error.codexActionFailed': NoMessageParameters
  readonly 'error.codexPairFailed': NoMessageParameters
  readonly 'error.claudeActionFailed': NoMessageParameters
  readonly 'error.doctorUnavailable': NoMessageParameters
  readonly 'error.projectIdentityChanged': NoMessageParameters
  readonly 'error.projectNotReady': NoMessageParameters
  readonly 'error.reconciliationRequired': NoMessageParameters
  readonly 'error.wawActionBusy': NoMessageParameters
  readonly 'error.wawActionFailed': NoMessageParameters
  readonly 'error.wawActionStale': NoMessageParameters
  readonly 'error.wawInvalidAgent': NoMessageParameters
  readonly 'error.wawMetadataInvalid': NoMessageParameters
  readonly 'error.wawSessionRequired': NoMessageParameters
  readonly 'error.wawStatusUnavailable': NoMessageParameters
  readonly 'error.workspaceNotFound': NoMessageParameters
}

export const errorCatalog = defineCatalogShard<ErrorMessageParameters>(
  'error',
  {
    en: {
      'error.unknown': () => 'The operation could not be completed. Try again.',
      'error.codeLabel': () => 'Error code',
      'error.requestIdLabel': () => 'Request ID',
      'error.authCsrfInvalid': () =>
        'Your session changed. Refresh and try again.',
      'error.authInvalidCredentials': () =>
        'The username or password is incorrect.',
      'error.authRateLimited': () =>
        'Too many sign-in attempts. Try again later.',
      'error.authRecentRequired': () =>
        'Sign in again before requesting a Codex pair code.',
      'error.authSessionInvalid': () =>
        'Your session is no longer valid. Sign in again.',
      'error.claudeRuntimeUnavailable': () =>
        'Claude is temporarily unavailable.',
      'error.codexRemoteStatusUnsupported': () =>
        'Codex Remote status is not supported by this installation.',
      'error.codexCommandTimeout': () =>
        'The Codex command did not finish in time.',
      'error.codexExecutableChanged': () =>
        'The Codex executable changed. Refresh and try again.',
      'error.codexExecutableInvalid': () =>
        'The configured Codex executable is not valid.',
      'error.codexNotInstalled': () => 'Codex is not installed.',
      'error.codexOutputLimitExceeded': () =>
        'Codex returned more output than AgentBox can safely process.',
      'error.codexPairOutputUnrecognized': () =>
        'Codex did not return a recognizable pair code.',
      'error.codexPairRateLimited': () =>
        'A Codex pair code was requested too recently. Try again later.',
      'error.codexPairTimeout': () =>
        'Codex did not create a pair code in time. Try again.',
      'error.codexPairUnsupported': () =>
        'This Codex installation does not support pair codes.',
      'error.codexRemoteStartFailed': () =>
        'Codex Remote could not be started.',
      'error.codexRemoteStopFailed': () => 'Codex Remote could not be stopped.',
      'error.codexRemoteUnsupported': () =>
        'This Codex installation does not support Remote controls.',
      'error.codexUnauthenticated': () =>
        'Authenticate Codex before requesting a pair code.',
      'error.projectNotFound': () => 'The requested Project was not found.',
      'error.controlPlaneUnavailable': () =>
        'The control plane is unavailable.',
      'error.requestTimeout': () => 'The request timed out. Try again.',
      'error.codexStatusUnavailable': () =>
        'Codex status is temporarily unavailable.',
      'error.codexActionFailed': () =>
        'The Codex operation could not be completed.',
      'error.codexPairFailed': () => 'A Codex pair code could not be created.',
      'error.claudeActionFailed': () =>
        'The Claude operation could not be completed.',
      'error.doctorUnavailable': () =>
        'Diagnostics are temporarily unavailable.',
      'error.projectIdentityChanged': () =>
        'The Project or Runtime identity changed. Refresh and try again.',
      'error.projectNotReady': () =>
        'This Project is not ready for the requested operation.',
      'error.reconciliationRequired': () =>
        'Runtime reconciliation is required before continuing.',
      'error.wawActionBusy': () =>
        'A workspace operation is already in progress.',
      'error.wawActionFailed': () =>
        'The workspace operation could not be completed.',
      'error.wawActionStale': () =>
        'The workspace state changed. Refresh and try again.',
      'error.wawInvalidAgent': () => 'The selected AgentType is not valid.',
      'error.wawMetadataInvalid': () =>
        'Workspace information is incomplete. Refresh and try again.',
      'error.wawSessionRequired': () =>
        'Sign in again before using the workspace.',
      'error.wawStatusUnavailable': () =>
        'Workspace status is temporarily unavailable.',
      'error.workspaceNotFound': () => 'The requested workspace was not found.',
    },
    'zh-CN': {
      'error.unknown': () => '操作未完成，请重试。',
      'error.codeLabel': () => '错误代码',
      'error.requestIdLabel': () => '请求 ID',
      'error.authCsrfInvalid': () => '会话已变化，请刷新后重试。',
      'error.authInvalidCredentials': () => '用户名或密码错误。',
      'error.authRateLimited': () => '登录尝试过于频繁，请稍后重试。',
      'error.authRecentRequired': () => '请重新登录后再请求 Codex 配对码。',
      'error.authSessionInvalid': () => '会话已失效，请重新登录。',
      'error.claudeRuntimeUnavailable': () => 'Claude 暂不可用。',
      'error.codexRemoteStatusUnsupported': () =>
        '当前安装不支持 Codex Remote 状态。',
      'error.codexCommandTimeout': () => 'Codex 命令未能及时完成。',
      'error.codexExecutableChanged': () =>
        'Codex 可执行文件已变化，请刷新后重试。',
      'error.codexExecutableInvalid': () => '配置的 Codex 可执行文件无效。',
      'error.codexNotInstalled': () => '尚未安装 Codex。',
      'error.codexOutputLimitExceeded': () =>
        'Codex 返回的输出超过 AgentBox 可安全处理的限制。',
      'error.codexPairOutputUnrecognized': () => 'Codex 未返回可识别的配对码。',
      'error.codexPairRateLimited': () =>
        'Codex 配对码请求过于频繁，请稍后重试。',
      'error.codexPairTimeout': () => 'Codex 未能及时创建配对码，请重试。',
      'error.codexPairUnsupported': () => '当前 Codex 安装不支持配对码。',
      'error.codexRemoteStartFailed': () => '无法启动 Codex Remote。',
      'error.codexRemoteStopFailed': () => '无法停止 Codex Remote。',
      'error.codexRemoteUnsupported': () =>
        '当前 Codex 安装不支持 Remote 控制。',
      'error.codexUnauthenticated': () => '请先完成 Codex 认证，再请求配对码。',
      'error.projectNotFound': () => '未找到请求的 Project。',
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
    },
  },
)
