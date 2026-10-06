import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { containDialogTab } from './dialogFocus'

afterEach(() => vi.restoreAllMocks())

describe('dialog Tab containment', () => {
  function setup() {
    vi.spyOn(Element.prototype, 'getClientRects').mockImplementation(function (
      this: HTMLElement,
    ) {
      return (this.style.display === 'none'
        ? []
        : [{}]) as unknown as DOMRectList
    })
    render(
      <dialog aria-label="Navigation" open onKeyDown={containDialogTab}>
        <button>First</button>
        <input aria-label="Search" />
        <a href="/projects">Last</a>
        <button disabled>Disabled</button>
        <button hidden>Hidden</button>
        <button style={{ display: 'none' }}>Invisible</button>
        <button tabIndex={-1}>Programmatic only</button>
      </dialog>,
    )
    return {
      first: screen.getByRole('button', { name: 'First' }),
      search: screen.getByRole('textbox'),
      last: screen.getByRole('link', { name: 'Last' }),
    }
  }

  it('wraps both edges, excluding hidden, disabled and negative-tabindex controls', () => {
    const { first, last } = setup()
    first.focus()
    expect(fireEvent.keyDown(first, { key: 'Tab', shiftKey: true })).toBe(false)
    expect(last).toHaveFocus()
    expect(fireEvent.keyDown(last, { key: 'Tab' })).toBe(false)
    expect(first).toHaveFocus()
  })

  it('preserves native interior traversal, Escape and browser shortcuts', () => {
    const { first, search, last } = setup()
    search.focus()
    expect(fireEvent.keyDown(search, { key: 'Tab' })).toBe(true)
    expect(fireEvent.keyDown(search, { key: 'Escape' })).toBe(true)
    last.focus()
    expect(fireEvent.keyDown(last, { key: 'Tab', ctrlKey: true })).toBe(true)
    expect(last).toHaveFocus()
    first.focus()
    expect(
      fireEvent.keyDown(first, { key: 'Tab', shiftKey: true, metaKey: true }),
    ).toBe(true)
  })
})
