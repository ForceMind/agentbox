import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface ProjectsMessageParameters {
  readonly 'projects.title': NoMessageParameters
  readonly 'projects.eyebrow': NoMessageParameters
  readonly 'projects.description': NoMessageParameters
  readonly 'projects.refresh': NoMessageParameters
  readonly 'projects.operationTitle': NoMessageParameters
  readonly 'projects.jobLabel': NoMessageParameters
  readonly 'projects.statusLabel': NoMessageParameters
  readonly 'projects.phaseLabel': NoMessageParameters
  readonly 'projects.progressLabel': NoMessageParameters
  readonly 'projects.progressValue': Readonly<{ progress: string }>
  readonly 'projects.jobQueued': NoMessageParameters
  readonly 'projects.jobRunning': NoMessageParameters
  readonly 'projects.jobSucceeded': NoMessageParameters
  readonly 'projects.jobFailed': NoMessageParameters
  readonly 'projects.jobCancelled': NoMessageParameters
  readonly 'projects.jobNeedsAttention': NoMessageParameters
  readonly 'projects.phaseQueued': NoMessageParameters
  readonly 'projects.phaseRunning': NoMessageParameters
  readonly 'projects.phaseExecuting': NoMessageParameters
  readonly 'projects.phaseRecoveryRequired': NoMessageParameters
  readonly 'projects.phaseSucceeded': NoMessageParameters
  readonly 'projects.phaseFailed': NoMessageParameters
  readonly 'projects.phaseCancelled': NoMessageParameters
  readonly 'projects.phaseNeedsAttention': NoMessageParameters
  readonly 'projects.emptyWorkspace': NoMessageParameters
  readonly 'projects.newProject': NoMessageParameters
  readonly 'projects.projectName': NoMessageParameters
  readonly 'projects.projectNameValidation': NoMessageParameters
  readonly 'projects.createProject': NoMessageParameters
  readonly 'projects.creatingProject': NoMessageParameters
  readonly 'projects.githubRepository': NoMessageParameters
  readonly 'projects.cloneRepository': NoMessageParameters
  readonly 'projects.repositoryUrl': NoMessageParameters
  readonly 'projects.repositoryPlaceholder': NoMessageParameters
  readonly 'projects.cloneProjectName': NoMessageParameters
  readonly 'projects.cloneUrlValidation': NoMessageParameters
  readonly 'projects.clone': NoMessageParameters
  readonly 'projects.cloning': NoMessageParameters
  readonly 'projects.loading': NoMessageParameters
  readonly 'projects.emptyTitle': NoMessageParameters
  readonly 'projects.emptyDescription': NoMessageParameters
  readonly 'projects.gridAria': NoMessageParameters
  readonly 'projects.stateCreating': NoMessageParameters
  readonly 'projects.stateReady': NoMessageParameters
  readonly 'projects.stateError': NoMessageParameters
  readonly 'projects.stateArchived': NoMessageParameters
  readonly 'projects.sourceCloned': NoMessageParameters
  readonly 'projects.sourceWorkspace': NoMessageParameters
  readonly 'projects.branch': NoMessageParameters
  readonly 'projects.changes': NoMessageParameters
  readonly 'projects.remote': NoMessageParameters
  readonly 'projects.claude': NoMessageParameters
  readonly 'projects.notInitialized': NoMessageParameters
  readonly 'projects.none': NoMessageParameters
  readonly 'projects.claudeRunning': NoMessageParameters
  readonly 'projects.claudeStopped': NoMessageParameters
  readonly 'projects.claudeStarting': NoMessageParameters
  readonly 'projects.claudeNeedsInteraction': NoMessageParameters
  readonly 'projects.claudeBroken': NoMessageParameters
  readonly 'projects.claudeUnknown': NoMessageParameters
}

export const projectsCatalog = defineCatalogShard<ProjectsMessageParameters>(
  'projects',
  {
    en: {
      'projects.title': () => 'Projects',
      'projects.eyebrow': () => 'Workspaces',
      'projects.description': () =>
        'Managed workspaces under the configured Project Root—never arbitrary filesystem paths.',
      'projects.refresh': () => 'Refresh',
      'projects.operationTitle': () => 'Workspace operation',
      'projects.jobLabel': () => 'Job',
      'projects.statusLabel': () => 'Status',
      'projects.phaseLabel': () => 'Phase',
      'projects.progressLabel': () => 'Progress',
      'projects.progressValue': ({ progress }) => `${progress}%`,
      'projects.jobQueued': () => 'Queued',
      'projects.jobRunning': () => 'Running',
      'projects.jobSucceeded': () => 'Succeeded',
      'projects.jobFailed': () => 'Failed',
      'projects.jobCancelled': () => 'Cancelled',
      'projects.jobNeedsAttention': () => 'Needs attention',
      'projects.phaseQueued': () => 'Queued',
      'projects.phaseRunning': () => 'Running',
      'projects.phaseExecuting': () => 'Executing',
      'projects.phaseRecoveryRequired': () => 'Recovery required',
      'projects.phaseSucceeded': () => 'Succeeded',
      'projects.phaseFailed': () => 'Failed',
      'projects.phaseCancelled': () => 'Cancelled',
      'projects.phaseNeedsAttention': () => 'Needs attention',
      'projects.emptyWorkspace': () => 'Empty workspace',
      'projects.newProject': () => 'New Project',
      'projects.projectName': () => 'Project name',
      'projects.projectNameValidation': () => 'Enter a Project name.',
      'projects.createProject': () => 'Create Project',
      'projects.creatingProject': () => 'Creating…',
      'projects.githubRepository': () => 'GitHub repository',
      'projects.cloneRepository': () => 'Clone Repository',
      'projects.repositoryUrl': () => 'Repository URL',
      'projects.repositoryPlaceholder': () => 'https://github.com/owner/repo',
      'projects.cloneProjectName': () => 'Project name (optional)',
      'projects.cloneUrlValidation': () => 'Enter a repository URL.',
      'projects.clone': () => 'Clone',
      'projects.cloning': () => 'Cloning…',
      'projects.loading': () => 'Loading Projects…',
      'projects.emptyTitle': () => 'No Projects yet',
      'projects.emptyDescription': () =>
        'Create a bounded workspace or clone an approved GitHub URL.',
      'projects.gridAria': () => 'Projects',
      'projects.stateCreating': () => 'Creating',
      'projects.stateReady': () => 'Ready',
      'projects.stateError': () => 'Error',
      'projects.stateArchived': () => 'Archived',
      'projects.sourceCloned': () => 'Cloned repository',
      'projects.sourceWorkspace': () => 'Workspace',
      'projects.branch': () => 'Branch',
      'projects.changes': () => 'Changes',
      'projects.remote': () => 'Remote',
      'projects.claude': () => 'Claude',
      'projects.notInitialized': () => 'Not initialized',
      'projects.none': () => 'None',
      'projects.claudeRunning': () => 'Running',
      'projects.claudeStopped': () => 'Stopped',
      'projects.claudeStarting': () => 'Starting',
      'projects.claudeNeedsInteraction': () => 'Needs interaction',
      'projects.claudeBroken': () => 'Broken',
      'projects.claudeUnknown': () => 'Unknown',
    },
    'zh-CN': {
      'projects.title': () => 'Projects',
      'projects.eyebrow': () => '工作区',
      'projects.description': () =>
        '管理已配置 Project Root 下的工作区，不接受任意文件系统路径。',
      'projects.refresh': () => '刷新',
      'projects.operationTitle': () => '工作区操作',
      'projects.jobLabel': () => 'Job',
      'projects.statusLabel': () => '状态',
      'projects.phaseLabel': () => '阶段',
      'projects.progressLabel': () => '进度',
      'projects.progressValue': ({ progress }) => `${progress}%`,
      'projects.jobQueued': () => '已排队',
      'projects.jobRunning': () => '运行中',
      'projects.jobSucceeded': () => '已成功',
      'projects.jobFailed': () => '失败',
      'projects.jobCancelled': () => '已取消',
      'projects.jobNeedsAttention': () => '需要处理',
      'projects.phaseQueued': () => '已排队',
      'projects.phaseRunning': () => '运行中',
      'projects.phaseExecuting': () => '正在执行',
      'projects.phaseRecoveryRequired': () => '需要恢复',
      'projects.phaseSucceeded': () => '已成功',
      'projects.phaseFailed': () => '失败',
      'projects.phaseCancelled': () => '已取消',
      'projects.phaseNeedsAttention': () => '需要处理',
      'projects.emptyWorkspace': () => '空工作区',
      'projects.newProject': () => '新建 Project',
      'projects.projectName': () => 'Project 名称',
      'projects.projectNameValidation': () => '请输入 Project 名称。',
      'projects.createProject': () => '创建 Project',
      'projects.creatingProject': () => '正在创建…',
      'projects.githubRepository': () => 'GitHub 仓库',
      'projects.cloneRepository': () => '克隆仓库',
      'projects.repositoryUrl': () => '仓库 URL',
      'projects.repositoryPlaceholder': () => 'https://github.com/owner/repo',
      'projects.cloneProjectName': () => 'Project 名称（可选）',
      'projects.cloneUrlValidation': () => '请输入仓库 URL。',
      'projects.clone': () => '克隆',
      'projects.cloning': () => '正在克隆…',
      'projects.loading': () => '正在加载 Projects…',
      'projects.emptyTitle': () => '还没有 Project',
      'projects.emptyDescription': () =>
        '创建一个受限工作区，或克隆已批准的 GitHub URL。',
      'projects.gridAria': () => 'Projects',
      'projects.stateCreating': () => '正在创建',
      'projects.stateReady': () => '已就绪',
      'projects.stateError': () => '异常',
      'projects.stateArchived': () => '已归档',
      'projects.sourceCloned': () => '克隆的仓库',
      'projects.sourceWorkspace': () => '工作区',
      'projects.branch': () => '分支',
      'projects.changes': () => '变更',
      'projects.remote': () => 'Remote',
      'projects.claude': () => 'Claude',
      'projects.notInitialized': () => '未初始化',
      'projects.none': () => '无',
      'projects.claudeRunning': () => '运行中',
      'projects.claudeStopped': () => '已停止',
      'projects.claudeStarting': () => '正在启动',
      'projects.claudeNeedsInteraction': () => '需要交互',
      'projects.claudeBroken': () => '异常',
      'projects.claudeUnknown': () => '未知',
    },
  },
)
