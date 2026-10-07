import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LogsPage } from './LogsPage'

describe('Logs remains a read-only product preview', () => {
  afterEach(() => vi.unstubAllGlobals())

  it.each([
    [
      'en',
      'Logs',
      'Not implemented yet',
      'Planned',
      'Planned Logs capabilities',
      ['AgentBox logs', 'Runtime logs', 'Audit events'],
      'This section is a product preview only. It does not invoke a runtime, system command, or host service.',
      [
        'Bounded control-plane diagnostics.',
        'Redacted runtime-specific output.',
        'Security-relevant action history.',
      ],
    ],
    [
      'zh-CN',
      '日志',
      '尚未实现',
      '计划中',
      '计划中的日志能力',
      ['AgentBox 日志', 'Runtime 日志', '审计事件'],
      '此区域仅展示产品预览，不会调用 Runtime、系统命令或主机服务。',
      [
        '有界的控制平面诊断信息。',
        '已脱敏的 Runtime 专用输出。',
        '与安全相关的操作历史。',
      ],
    ],
  ] as const)(
    'exposes exactly three planned capabilities without reads or actions in %s',
    (
      locale,
      title,
      unavailable,
      planned,
      label,
      capabilities,
      disclaimer,
      descriptions,
    ) => {
      const fetchMock = vi.fn(() => {
        throw new Error('Logs must not make a request')
      })
      vi.stubGlobal('fetch', fetchMock)
      const { container, rerender } = render(<LogsPage locale={locale} />)

      expect(
        screen.getByRole('heading', { name: title, level: 1 }),
      ).toBeVisible()
      expect(screen.getByRole('heading', { name: unavailable })).toBeVisible()
      expect(screen.getByText(disclaimer)).toBeVisible()
      const region = screen.getByRole('region', { name: label })
      expect(within(region).getAllByRole('article')).toHaveLength(3)
      for (const [index, article] of within(region)
        .getAllByRole('article')
        .entries()) {
        expect(
          within(article).getByRole('heading', { name: capabilities[index] }),
        ).toBeVisible()
        expect(within(article).getByText(planned)).toBeVisible()
        expect(within(article).getByText(descriptions[index])).toBeVisible()
      }
      expect(
        container.querySelector(
          'button, input, select, textarea, form, a, table, [role="log"], [contenteditable="true"]',
        ),
      ).toBeNull()
      rerender(<LogsPage locale={locale === 'en' ? 'zh-CN' : 'en'} />)
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )
})
