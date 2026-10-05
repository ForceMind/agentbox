import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { VerifiedPatchView } from './VerifiedPatchView'

afterEach(cleanup)
const source =
  'diff --git a/f b/f\nindex 1111111..2222222 100644\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-旧\r\n+<img src=x onerror=alert(1)>\t🌍\r\n\\ No newline at end of file\n'
describe('completed-owner inert diff view', () => {
  it('renders semantic columns, hunk rows and explicit kinds without source-generated elements', () => {
    render(<VerifiedPatchView text={source} />)
    expect(screen.getByTestId('unified-diff-table').tagName).toBe('TABLE')
    for (const name of ['旧行', '新行', '补丁文本'])
      expect(screen.getByRole('columnheader', { name })).toBeVisible()
    expect(screen.getByText('@@ -1 +1 @@')).toBeVisible()
    expect(
      screen.getAllByTestId('diff-line-text').map((node) => node.textContent),
    ).toEqual([
      '-旧\r',
      '+<img src=x onerror=alert(1)>\t🌍\r',
      '\\ No newline at end of file',
    ])
    expect(
      screen
        .getByTestId('a3-complete-patch')
        .querySelector('img,script,svg,a,iframe'),
    ).toBeNull()
    expect(screen.getByText('增加：')).toBeInTheDocument()
    expect(screen.getByText('删除：')).toBeInTheDocument()
    expect(screen.getByText(/行号仅为补丁声明/)).toBeVisible()
    expect(screen.getByTestId('a3-complete-patch')).toHaveAttribute(
      'tabindex',
      '0',
    )
  })
  it('repeated view/wrap switches preserve exactly the original string, without retaining hidden raw DOM', () => {
    const result = render(<VerifiedPatchView text={source} />)
    const wrap = screen.getByRole('checkbox', { name: '换行显示' })
    expect(wrap).toBeChecked()
    for (let attempt = 0; attempt < 3; attempt++) {
      fireEvent.click(screen.getByRole('button', { name: '原文' }))
      expect(screen.getByRole('button', { name: '原文' })).toHaveAttribute(
        'aria-pressed',
        'true',
      )
      expect(screen.getByTestId('a3-complete-patch').textContent).toBe(source)
      expect(screen.queryByTestId('unified-diff-table')).toBeNull()
      fireEvent.click(wrap)
      expect(screen.getByTestId('a3-complete-patch')).toHaveClass(
        'diff-no-wrap',
      )
      fireEvent.click(wrap)
      fireEvent.click(screen.getByRole('button', { name: '统一视图' }))
      expect(screen.getByRole('button', { name: '统一视图' })).toHaveAttribute(
        'aria-pressed',
        'true',
      )
      expect(screen.getByTestId('unified-diff-table')).toBeVisible()
    }
    result.unmount()
    expect(screen.queryByTestId('a3-complete-patch')).toBeNull()
    expect(document.body.textContent).not.toContain('onerror')
  })
  it.each([
    'legacy plain <svg/onload=alert(1)>\r\n\t🌍',
    source.replace('+<img', '+\0<img'),
    source.replace('@@ -1 +1 @@', '@@ -1,2 +1 @@'),
    'x'.repeat(8193) + '\r\nEND',
    '🌍'.repeat(70000) + '\r\nEND',
  ])('shows complete exact fallback without unified controls %#', (text) => {
    render(<VerifiedPatchView text={text} />)
    expect(screen.getByTestId('a3-complete-patch').textContent).toBe(text)
    expect(screen.getByText(/已显示完整原文，未截断/)).toBeVisible()
    expect(screen.queryByRole('button', { name: '统一视图' })).toBeNull()
    expect(screen.queryByTestId('unified-diff-table')).toBeNull()
    expect(
      screen.getByTestId('a3-complete-patch').querySelector('img,script,svg,a'),
    ).toBeNull()
  })
})
