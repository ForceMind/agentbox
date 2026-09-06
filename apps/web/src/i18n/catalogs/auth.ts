import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'
import { formatPlural } from '../formatters'

export interface AuthMessageParameters {
  readonly 'auth.title': NoMessageParameters
  readonly 'auth.restoringSession': NoMessageParameters
  readonly 'auth.productCategory': NoMessageParameters
  readonly 'auth.heading': NoMessageParameters
  readonly 'auth.description': NoMessageParameters
  readonly 'auth.username': NoMessageParameters
  readonly 'auth.usernamePlaceholder': NoMessageParameters
  readonly 'auth.password': NoMessageParameters
  readonly 'auth.passwordPlaceholder': NoMessageParameters
  readonly 'auth.signingIn': NoMessageParameters
  readonly 'auth.signIn': NoMessageParameters
  readonly 'auth.retryAfter': Readonly<{ seconds: number }>
  readonly 'auth.requestDetails': NoMessageParameters
  readonly 'auth.localAdministratorOnly': NoMessageParameters
  readonly 'auth.version': NoMessageParameters
  readonly 'auth.productContextLabel': NoMessageParameters
  readonly 'auth.contextEyebrow': NoMessageParameters
  readonly 'auth.contextHeading': NoMessageParameters
  readonly 'auth.contextDescription': NoMessageParameters
  readonly 'auth.loopbackAccess': NoMessageParameters
  readonly 'auth.serverSessions': NoMessageParameters
  readonly 'auth.noBrowserShell': NoMessageParameters
}

export const authCatalog = defineCatalogShard<AuthMessageParameters>('auth', {
  en: {
    'auth.title': () => 'Sign in',
    'auth.restoringSession': () => 'Restoring your session…',
    'auth.productCategory': () => 'AI Developer Infrastructure',
    'auth.heading': () => 'Sign in to manage this workstation',
    'auth.description': () =>
      'Use the local administrator initialized with the AgentBox CLI.',
    'auth.username': () => 'Username',
    'auth.usernamePlaceholder': () => 'Enter your username',
    'auth.password': () => 'Password',
    'auth.passwordPlaceholder': () => 'Enter your password',
    'auth.signingIn': () => 'Signing in…',
    'auth.signIn': () => 'Sign in',
    'auth.retryAfter': ({ seconds }) =>
      formatPlural('en', seconds, {
        one: ({ formattedCount }) =>
          `Try again in approximately ${formattedCount} second.`,
        other: ({ formattedCount }) =>
          `Try again in approximately ${formattedCount} seconds.`,
      }),
    'auth.requestDetails': () => 'Request details',
    'auth.localAdministratorOnly': () => 'Local administrator access only',
    'auth.version': () => 'Version',
    'auth.productContextLabel': () => 'AgentBox product context',
    'auth.contextEyebrow': () => 'One workstation. One calm control plane.',
    'auth.contextHeading': () =>
      'Keep AI development infrastructure within reach.',
    'auth.contextDescription': () =>
      'AgentBox is building a secure, remote management layer for a Linux AI development workstation. Runtime controls arrive in later phases.',
    'auth.loopbackAccess': () => 'Loopback-first access',
    'auth.serverSessions': () => 'Server-side sessions',
    'auth.noBrowserShell': () => 'No browser shell',
  },
  'zh-CN': {
    'auth.title': () => '登录',
    'auth.restoringSession': () => '正在恢复会话…',
    'auth.productCategory': () => 'AI 开发基础设施',
    'auth.heading': () => '登录以管理此工作站',
    'auth.description': () =>
      '请使用通过 AgentBox CLI 初始化的本地管理员账户。',
    'auth.username': () => '用户名',
    'auth.usernamePlaceholder': () => '请输入用户名',
    'auth.password': () => '密码',
    'auth.passwordPlaceholder': () => '请输入密码',
    'auth.signingIn': () => '正在登录…',
    'auth.signIn': () => '登录',
    'auth.retryAfter': ({ seconds }) =>
      `请大约 ${formatPlural('zh-CN', seconds, {
        other: ({ formattedCount }) => formattedCount,
      })} 秒后重试。`,
    'auth.requestDetails': () => '请求详情',
    'auth.localAdministratorOnly': () => '仅限本地管理员访问',
    'auth.version': () => '版本',
    'auth.productContextLabel': () => 'AgentBox 产品简介',
    'auth.contextEyebrow': () => '一台工作站，一个从容的控制平面。',
    'auth.contextHeading': () => '随时掌控 AI 开发基础设施。',
    'auth.contextDescription': () =>
      'AgentBox 正在为 Linux AI 开发工作站构建安全的远程管理层。Runtime 控制能力将在后续阶段提供。',
    'auth.loopbackAccess': () => '优先通过回环地址访问',
    'auth.serverSessions': () => '服务端会话',
    'auth.noBrowserShell': () => '浏览器不提供 shell',
  },
})
