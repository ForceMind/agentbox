import { defineCatalogShard } from './types'
import type { NoMessageParameters } from './types'

export interface ProjectMessageParameters {
  readonly 'project.title': NoMessageParameters
  readonly 'project.backToProjects': NoMessageParameters
  readonly 'project.loading': NoMessageParameters
  readonly 'project.unavailableTitle': NoMessageParameters
  readonly 'project.eyebrow': NoMessageParameters
  readonly 'project.description': NoMessageParameters
  readonly 'project.workspace': NoMessageParameters
  readonly 'project.slug': NoMessageParameters
  readonly 'project.source': NoMessageParameters
  readonly 'project.sourceEmpty': NoMessageParameters
  readonly 'project.sourceGitClone': NoMessageParameters
  readonly 'project.sourceExisting': NoMessageParameters
  readonly 'project.stateCreating': NoMessageParameters
  readonly 'project.stateReady': NoMessageParameters
  readonly 'project.stateError': NoMessageParameters
  readonly 'project.stateArchived': NoMessageParameters
  readonly 'project.openWorkspace': NoMessageParameters
  readonly 'project.git': NoMessageParameters
  readonly 'project.gitClean': NoMessageParameters
  readonly 'project.gitChanges': Readonly<{ count: string }>
  readonly 'project.notInitialized': NoMessageParameters
  readonly 'project.branch': NoMessageParameters
  readonly 'project.detachedHead': NoMessageParameters
  readonly 'project.unbornBranch': NoMessageParameters
  readonly 'project.aheadBehind': NoMessageParameters
  readonly 'project.remote': NoMessageParameters
  readonly 'project.none': NoMessageParameters
  readonly 'project.stagedUnstaged': NoMessageParameters
  readonly 'project.untrackedConflicted': NoMessageParameters
  readonly 'project.submodulesDetected': NoMessageParameters
  readonly 'project.gitActionsTitle': NoMessageParameters
  readonly 'project.gitActionsDescription': NoMessageParameters
  readonly 'project.pull': NoMessageParameters
  readonly 'project.pulling': NoMessageParameters
  readonly 'project.push': NoMessageParameters
  readonly 'project.pushing': NoMessageParameters
  readonly 'project.branchName': NoMessageParameters
  readonly 'project.branchPlaceholder': NoMessageParameters
  readonly 'project.createBranch': NoMessageParameters
  readonly 'project.creatingBranch': NoMessageParameters
  readonly 'project.switchBranch': NoMessageParameters
  readonly 'project.switchingBranch': NoMessageParameters
  readonly 'project.localBranches': NoMessageParameters
  readonly 'project.currentBranch': NoMessageParameters
  readonly 'project.github': NoMessageParameters
  readonly 'project.repository': NoMessageParameters
  readonly 'project.checks': NoMessageParameters
  readonly 'project.checksPass': NoMessageParameters
  readonly 'project.checksFail': NoMessageParameters
  readonly 'project.checksPending': NoMessageParameters
  readonly 'project.checksUnknown': NoMessageParameters
  readonly 'project.githubUnavailable': NoMessageParameters
  readonly 'project.currentBranchPr': NoMessageParameters
  readonly 'project.untitled': NoMessageParameters
  readonly 'project.prState': NoMessageParameters
  readonly 'project.prStateOpen': NoMessageParameters
  readonly 'project.prStateClosed': NoMessageParameters
  readonly 'project.prStateMerged': NoMessageParameters
  readonly 'project.draft': NoMessageParameters
  readonly 'project.baseHead': NoMessageParameters
  readonly 'project.mergeability': NoMessageParameters
  readonly 'project.mergeabilityBehind': NoMessageParameters
  readonly 'project.mergeabilityBlocked': NoMessageParameters
  readonly 'project.mergeabilityClean': NoMessageParameters
  readonly 'project.mergeabilityDirty': NoMessageParameters
  readonly 'project.mergeabilityDraft': NoMessageParameters
  readonly 'project.mergeabilityHasHooks': NoMessageParameters
  readonly 'project.mergeabilityUnstable': NoMessageParameters
  readonly 'project.unknown': NoMessageParameters
  readonly 'project.prTitle': NoMessageParameters
  readonly 'project.prTitlePlaceholder': NoMessageParameters
  readonly 'project.prBase': NoMessageParameters
  readonly 'project.prBasePlaceholder': NoMessageParameters
  readonly 'project.prBody': NoMessageParameters
  readonly 'project.prBodyPlaceholder': NoMessageParameters
  readonly 'project.createDraftPr': NoMessageParameters
  readonly 'project.creatingDraftPr': NoMessageParameters
  readonly 'project.claudeSession': NoMessageParameters
  readonly 'project.claudeLoading': NoMessageParameters
  readonly 'project.claudeUnavailable': NoMessageParameters
  readonly 'project.claudeRunning': NoMessageParameters
  readonly 'project.claudeStopped': NoMessageParameters
  readonly 'project.claudeStarting': NoMessageParameters
  readonly 'project.claudeNeedsInteraction': NoMessageParameters
  readonly 'project.claudeBroken': NoMessageParameters
  readonly 'project.claudeUnknown': NoMessageParameters
  readonly 'project.claudeDescription': NoMessageParameters
  readonly 'project.stopClaude': NoMessageParameters
  readonly 'project.stoppingClaude': NoMessageParameters
  readonly 'project.startClaude': NoMessageParameters
  readonly 'project.startingClaude': NoMessageParameters
  readonly 'project.latestOperation': NoMessageParameters
  readonly 'project.jobLabel': NoMessageParameters
  readonly 'project.statusLabel': NoMessageParameters
  readonly 'project.phaseLabel': NoMessageParameters
  readonly 'project.progressLabel': NoMessageParameters
  readonly 'project.progressValue': Readonly<{ progress: string }>
  readonly 'project.jobQueued': NoMessageParameters
  readonly 'project.jobRunning': NoMessageParameters
  readonly 'project.jobSucceeded': NoMessageParameters
  readonly 'project.jobFailed': NoMessageParameters
  readonly 'project.jobCancelled': NoMessageParameters
  readonly 'project.jobNeedsAttention': NoMessageParameters
  readonly 'project.phaseQueued': NoMessageParameters
  readonly 'project.phaseRunning': NoMessageParameters
  readonly 'project.phaseExecuting': NoMessageParameters
  readonly 'project.phaseRecoveryRequired': NoMessageParameters
  readonly 'project.phaseSucceeded': NoMessageParameters
  readonly 'project.phaseFailed': NoMessageParameters
  readonly 'project.phaseCancelled': NoMessageParameters
  readonly 'project.phaseNeedsAttention': NoMessageParameters
}

export const projectCatalog = defineCatalogShard<ProjectMessageParameters>(
  'project',
  {
    en: {
      'project.title': () => 'Project',
      'project.backToProjects': () => 'Projects',
      'project.loading': () => 'Loading Project…',
      'project.unavailableTitle': () => 'Project unavailable',
      'project.eyebrow': () => 'Project Workspace',
      'project.description': () =>
        'Git operations are typed, serialized, and executed without a shell.',
      'project.workspace': () => 'Workspace',
      'project.slug': () => 'Slug',
      'project.source': () => 'Source',
      'project.sourceEmpty': () => 'Empty workspace',
      'project.sourceGitClone': () => 'Git clone',
      'project.sourceExisting': () => 'Existing workspace',
      'project.stateCreating': () => 'Creating',
      'project.stateReady': () => 'Ready',
      'project.stateError': () => 'Error',
      'project.stateArchived': () => 'Archived',
      'project.openWorkspace': () => 'Open Interactive Workspace',
      'project.git': () => 'Git',
      'project.gitClean': () => 'Clean',
      'project.gitChanges': ({ count }) => `${count} changes`,
      'project.notInitialized': () => 'Not initialized',
      'project.branch': () => 'Branch',
      'project.detachedHead': () => 'Detached HEAD',
      'project.unbornBranch': () => 'Unborn',
      'project.aheadBehind': () => 'Ahead / behind',
      'project.remote': () => 'Remote',
      'project.none': () => 'None',
      'project.stagedUnstaged': () => 'Staged / unstaged',
      'project.untrackedConflicted': () => 'Untracked / conflicted',
      'project.submodulesDetected': () =>
        'Submodules detected — automatic initialization is not supported.',
      'project.gitActionsTitle': () => 'Safe Git actions',
      'project.gitActionsDescription': () =>
        'Pull is fast-forward only. Push never forces. Active Claude sessions block Pull and branch switching.',
      'project.pull': () => 'Pull',
      'project.pulling': () => 'Pulling…',
      'project.push': () => 'Push',
      'project.pushing': () => 'Pushing…',
      'project.branchName': () => 'Branch name',
      'project.branchPlaceholder': () => 'feature/name',
      'project.createBranch': () => 'Create branch',
      'project.creatingBranch': () => 'Creating…',
      'project.switchBranch': () => 'Switch branch',
      'project.switchingBranch': () => 'Switching…',
      'project.localBranches': () => 'Local branches',
      'project.currentBranch': () => 'Current',
      'project.github': () => 'GitHub',
      'project.repository': () => 'Repository',
      'project.checks': () => 'checks',
      'project.checksPass': () => 'pass',
      'project.checksFail': () => 'fail',
      'project.checksPending': () => 'pending',
      'project.checksUnknown': () => 'unknown',
      'project.githubUnavailable': () =>
        'GitHub features unavailable for this Project.',
      'project.currentBranchPr': () => 'Current branch PR',
      'project.untitled': () => 'Untitled',
      'project.prState': () => 'State',
      'project.prStateOpen': () => 'Open',
      'project.prStateClosed': () => 'Closed',
      'project.prStateMerged': () => 'Merged',
      'project.draft': () => 'Draft',
      'project.baseHead': () => 'Base / head',
      'project.mergeability': () => 'Mergeability',
      'project.mergeabilityBehind': () => 'Behind',
      'project.mergeabilityBlocked': () => 'Blocked',
      'project.mergeabilityClean': () => 'Clean',
      'project.mergeabilityDirty': () => 'Dirty',
      'project.mergeabilityDraft': () => 'Draft',
      'project.mergeabilityHasHooks': () => 'Has hooks',
      'project.mergeabilityUnstable': () => 'Unstable',
      'project.unknown': () => 'Unknown',
      'project.prTitle': () => 'Pull request title',
      'project.prTitlePlaceholder': () => 'Draft PR title',
      'project.prBase': () => 'Pull request base branch',
      'project.prBasePlaceholder': () => 'Base branch (optional)',
      'project.prBody': () => 'Pull request body',
      'project.prBodyPlaceholder': () =>
        'Draft PR body (do not paste credentials)',
      'project.createDraftPr': () => 'Create Draft PR',
      'project.creatingDraftPr': () => 'Creating…',
      'project.claudeSession': () => 'Claude session',
      'project.claudeLoading': () => 'Loading',
      'project.claudeUnavailable': () => 'Unavailable',
      'project.claudeRunning': () => 'Running',
      'project.claudeStopped': () => 'Stopped',
      'project.claudeStarting': () => 'Starting',
      'project.claudeNeedsInteraction': () => 'Needs interaction',
      'project.claudeBroken': () => 'Broken',
      'project.claudeUnknown': () => 'Unknown',
      'project.claudeDescription': () =>
        'Branch switching and Pull are blocked while this managed session is active.',
      'project.stopClaude': () => 'Stop Claude',
      'project.stoppingClaude': () => 'Stopping…',
      'project.startClaude': () => 'Start Claude',
      'project.startingClaude': () => 'Starting…',
      'project.latestOperation': () => 'Latest operation',
      'project.jobLabel': () => 'Job',
      'project.statusLabel': () => 'Status',
      'project.phaseLabel': () => 'Phase',
      'project.progressLabel': () => 'Progress',
      'project.progressValue': ({ progress }) => `${progress}%`,
      'project.jobQueued': () => 'Queued',
      'project.jobRunning': () => 'Running',
      'project.jobSucceeded': () => 'Succeeded',
      'project.jobFailed': () => 'Failed',
      'project.jobCancelled': () => 'Cancelled',
      'project.jobNeedsAttention': () => 'Needs attention',
      'project.phaseQueued': () => 'Queued',
      'project.phaseRunning': () => 'Running',
      'project.phaseExecuting': () => 'Executing',
      'project.phaseRecoveryRequired': () => 'Recovery required',
      'project.phaseSucceeded': () => 'Succeeded',
      'project.phaseFailed': () => 'Failed',
      'project.phaseCancelled': () => 'Cancelled',
      'project.phaseNeedsAttention': () => 'Needs attention',
    },
    'zh-CN': {
      'project.title': () => 'Project',
      'project.backToProjects': () => 'Projects',
      'project.loading': () => '正在加载 Project…',
      'project.unavailableTitle': () => 'Project 不可用',
      'project.eyebrow': () => 'Project 工作区',
      'project.description': () =>
        'Git 操作采用固定类型并按顺序执行，不会启动 shell。',
      'project.workspace': () => '工作区',
      'project.slug': () => 'Slug',
      'project.source': () => '来源',
      'project.sourceEmpty': () => '空工作区',
      'project.sourceGitClone': () => 'Git 克隆',
      'project.sourceExisting': () => '现有工作区',
      'project.stateCreating': () => '正在创建',
      'project.stateReady': () => '已就绪',
      'project.stateError': () => '异常',
      'project.stateArchived': () => '已归档',
      'project.openWorkspace': () => '打开交互式工作区',
      'project.git': () => 'Git',
      'project.gitClean': () => '干净',
      'project.gitChanges': ({ count }) => `${count} 项变更`,
      'project.notInitialized': () => '未初始化',
      'project.branch': () => '分支',
      'project.detachedHead': () => 'Detached HEAD',
      'project.unbornBranch': () => '尚无提交',
      'project.aheadBehind': () => '领先 / 落后',
      'project.remote': () => 'Remote',
      'project.none': () => '无',
      'project.stagedUnstaged': () => '已暂存 / 未暂存',
      'project.untrackedConflicted': () => '未跟踪 / 冲突',
      'project.submodulesDetected': () =>
        '检测到 submodule，暂不支持自动初始化。',
      'project.gitActionsTitle': () => '安全 Git 操作',
      'project.gitActionsDescription': () =>
        'Pull 仅允许 fast-forward；Push 绝不强制执行。Claude 会话活动期间不能 Pull 或切换分支。',
      'project.pull': () => 'Pull',
      'project.pulling': () => '正在 Pull…',
      'project.push': () => 'Push',
      'project.pushing': () => '正在 Push…',
      'project.branchName': () => '分支名称',
      'project.branchPlaceholder': () => 'feature/name',
      'project.createBranch': () => '创建分支',
      'project.creatingBranch': () => '正在创建…',
      'project.switchBranch': () => '切换分支',
      'project.switchingBranch': () => '正在切换…',
      'project.localBranches': () => '本地分支',
      'project.currentBranch': () => '当前',
      'project.github': () => 'GitHub',
      'project.repository': () => '仓库',
      'project.checks': () => '检查',
      'project.checksPass': () => '通过',
      'project.checksFail': () => '失败',
      'project.checksPending': () => '进行中',
      'project.checksUnknown': () => '未知',
      'project.githubUnavailable': () => '此 Project 无法使用 GitHub 功能。',
      'project.currentBranchPr': () => '当前分支 PR',
      'project.untitled': () => '无标题',
      'project.prState': () => '状态',
      'project.prStateOpen': () => '开放',
      'project.prStateClosed': () => '已关闭',
      'project.prStateMerged': () => '已合并',
      'project.draft': () => '草稿',
      'project.baseHead': () => 'Base / head',
      'project.mergeability': () => '可合并状态',
      'project.mergeabilityBehind': () => '落后',
      'project.mergeabilityBlocked': () => '受阻',
      'project.mergeabilityClean': () => '可合并',
      'project.mergeabilityDirty': () => '存在冲突',
      'project.mergeabilityDraft': () => '草稿',
      'project.mergeabilityHasHooks': () => '有 hooks',
      'project.mergeabilityUnstable': () => '不稳定',
      'project.unknown': () => '未知',
      'project.prTitle': () => 'Pull request 标题',
      'project.prTitlePlaceholder': () => 'Draft PR 标题',
      'project.prBase': () => 'Pull request base 分支',
      'project.prBasePlaceholder': () => 'Base 分支（可选）',
      'project.prBody': () => 'Pull request 正文',
      'project.prBodyPlaceholder': () => 'Draft PR 正文（请勿粘贴凭据）',
      'project.createDraftPr': () => '创建 Draft PR',
      'project.creatingDraftPr': () => '正在创建…',
      'project.claudeSession': () => 'Claude 会话',
      'project.claudeLoading': () => '正在加载',
      'project.claudeUnavailable': () => '不可用',
      'project.claudeRunning': () => '运行中',
      'project.claudeStopped': () => '已停止',
      'project.claudeStarting': () => '正在启动',
      'project.claudeNeedsInteraction': () => '需要交互',
      'project.claudeBroken': () => '异常',
      'project.claudeUnknown': () => '未知',
      'project.claudeDescription': () =>
        '此托管会话活动期间不能切换分支或 Pull。',
      'project.stopClaude': () => '停止 Claude',
      'project.stoppingClaude': () => '正在停止…',
      'project.startClaude': () => '启动 Claude',
      'project.startingClaude': () => '正在启动…',
      'project.latestOperation': () => '最近操作',
      'project.jobLabel': () => 'Job',
      'project.statusLabel': () => '状态',
      'project.phaseLabel': () => '阶段',
      'project.progressLabel': () => '进度',
      'project.progressValue': ({ progress }) => `${progress}%`,
      'project.jobQueued': () => '已排队',
      'project.jobRunning': () => '运行中',
      'project.jobSucceeded': () => '已成功',
      'project.jobFailed': () => '失败',
      'project.jobCancelled': () => '已取消',
      'project.jobNeedsAttention': () => '需要处理',
      'project.phaseQueued': () => '已排队',
      'project.phaseRunning': () => '运行中',
      'project.phaseExecuting': () => '正在执行',
      'project.phaseRecoveryRequired': () => '需要恢复',
      'project.phaseSucceeded': () => '已成功',
      'project.phaseFailed': () => '失败',
      'project.phaseCancelled': () => '已取消',
      'project.phaseNeedsAttention': () => '需要处理',
    },
  },
)
