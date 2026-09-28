import { searchProjects } from '../features/projects/searchProjects'
import type { ProjectData } from '../lib/contracts'

export type CommandCenterAction = Readonly<{ title: string; href: string }>

export type CommandResult =
  | Readonly<{ kind: 'action'; id: string; title: string; href: string }>
  | Readonly<{
      kind: 'project'
      id: string
      project: ProjectData
      href: string
    }>

const FORMAL_PROJECT_ID = /^prj_[0-9a-f]{32}$/u
const FIXED_PAGE =
  /^\/(?:dashboard|attention|codex|claude|workspace|projects|doctor|logs|settings)$/u

function actionMatches(action: CommandCenterAction, query: string): boolean {
  const tokens = query.trim().toLowerCase().split(/\s+/u).filter(Boolean)
  const title = action.title.toLowerCase()
  return tokens.every((token) => title.includes(token))
}

export function commandResults(
  actions: readonly CommandCenterAction[],
  projects: readonly ProjectData[],
  query: string,
): CommandResult[] {
  const searching = Boolean(query.trim())
  const matchedActions = actions
    .filter(
      (action) =>
        FIXED_PAGE.test(action.href) &&
        (!searching || actionMatches(action, query)),
    )
    .map((action) => ({
      kind: 'action' as const,
      id: `action:${action.href}`,
      title: action.title,
      href: action.href,
    }))
  const matchedProjects = searchProjects(
    projects.filter((project) => FORMAL_PROJECT_ID.test(project.id)),
    query,
  )
    .slice(0, searching ? 32 : 5)
    .map((project) => ({
      kind: 'project' as const,
      id: `project:${project.id}`,
      project,
      href: `/projects/${project.id}`,
    }))
  return [...matchedActions, ...matchedProjects]
}
