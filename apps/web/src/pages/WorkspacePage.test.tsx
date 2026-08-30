import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { WorkspacePage } from './WorkspacePage'
import { WorkspaceState } from '../features/workspace/workspaceState'

const workspaceId = 'aws_0123456789abcdef0123456789abcdef'

function state(status: WorkspaceState['status']): WorkspaceState {
  return {
    status,
    projectId: 'prj_0123456789abcdef0123456789abcdef',
    workspaceId,
    agentType: 'claude',
    errorCode: status === 'error' ? 'RUNTIME_UNAVAILABLE' : null,
    message: null,
  }
}

describe('WorkspacePage security UI skeleton', () => {
  it('starts unadmitted and keeps actions disabled until transport exists', () => {
    render(<WorkspacePage />)

    expect(
      screen.getByRole('heading', { name: 'Interactive Workspace' }),
    ).toBeInTheDocument()
    expect(screen.getByText('检查中')).toBeInTheDocument()
    expect(screen.getByText('NOT ADMITTED')).toBeInTheDocument()
    expect(
      screen.getByText(/不会伪造 workspace、ticket 或运行状态/),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Start / Connect' }),
    ).toBeDisabled()
    expect(
      screen.getByRole('button', { name: /Stop workspace/ }),
    ).toBeDisabled()
  })

  it.each([
    ['starting', '启动中'],
    ['connecting', '连接中'],
    ['connected', '已连接'],
    ['reconnecting', '重新连接中'],
    ['error', '错误'],
    ['stopping', '停止中'],
    ['detached', '已分离'],
    ['stopped', '已停止'],
    ['gap', '输出有缺口'],
    ['input_uncertain', '输入状态不确定'],
  ] as const)('renders %s as a distinct state', (status, label) => {
    render(<WorkspacePage initialState={state(status)} />)

    expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.getByText(status)).toBeInTheDocument()
  })

  it('shows the ADMITTED marker only for connected state', () => {
    const { rerender } = render(
      <WorkspacePage initialState={state('connecting')} />,
    )
    expect(screen.getByText('NOT ADMITTED')).toBeInTheDocument()
    expect(
      screen.queryByText('Runtime ADMITTED 已确认'),
    ).not.toBeInTheDocument()

    rerender(<WorkspacePage initialState={state('connected')} />)
    expect(screen.getByText('ADMITTED')).toBeInTheDocument()
    expect(screen.getByText(/Runtime ADMITTED 已确认/)).toBeInTheDocument()
  })

  it('keeps sensitive terminal data out of browser storage and exposes no transcript action', () => {
    render(<WorkspacePage initialState={state('connected')} />)

    expect(screen.getByText(/不会保存 transcript、ticket/)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /transcript|下载/i }),
    ).not.toBeInTheDocument()
    expect(window.localStorage).toHaveLength(0)
    expect(window.sessionStorage).toHaveLength(0)
  })
})
