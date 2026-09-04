import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  AuthContext,
  type AuthContextValue,
} from '../features/auth/AuthContext'
import { ApiClient } from '../lib/api'
import { ControlPlanePulse } from './ControlPlanePulse'

function authContext(api: ApiClient): AuthContextValue {
  return {
    api,
    auth: null,
    status: 'authenticated',
    login: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    refresh: vi.fn(async () => null),
  }
}

describe('ControlPlanePulse', () => {
  it('uses the selected locale for successful health state', async () => {
    const api = {
      get: vi.fn(async () => ({ status: 'ok' })),
    } as unknown as ApiClient

    render(
      <AuthContext.Provider value={authContext(api)}>
        <ControlPlanePulse locale="en" />
      </AuthContext.Provider>,
    )

    expect(screen.getByLabelText('Control plane: Checking')).toBeVisible()
    expect(await screen.findByLabelText('Control plane: Healthy')).toBeVisible()
  })

  it('uses Chinese copy only when zh-CN is selected', async () => {
    const api = {
      get: vi.fn(async () => ({ status: 'not-ok' })),
    } as unknown as ApiClient

    render(
      <AuthContext.Provider value={authContext(api)}>
        <ControlPlanePulse locale="zh-CN" />
      </AuthContext.Provider>,
    )

    expect(screen.getByLabelText('控制平面: 检查中')).toBeVisible()
    expect(await screen.findByLabelText('控制平面: 不可用')).toBeVisible()
  })
})
