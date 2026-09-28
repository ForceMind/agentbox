export const MESSAGE_DOMAINS = Object.freeze([
  'app',
  'common',
  'items',
  'document',
  'error',
  'shell',
  'auth',
  'dashboard',
  'attention',
  'codex',
  'claude',
  'workspace',
  'projects',
  'project',
  'doctor',
  'logs',
  'settings',
  'notFound',
] as const)

export type MessageDomain = (typeof MESSAGE_DOMAINS)[number]
