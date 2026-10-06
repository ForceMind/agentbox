import type { KeyboardEvent } from 'react'

/** Keep Tab traversal inside the modal's controls, including at browser-UI edges.
 * Native showModal still owns top-layer placement and outside-document inertness.
 */
export function containDialogTab(event: KeyboardEvent<HTMLDialogElement>) {
  if (
    event.defaultPrevented ||
    event.key !== 'Tab' ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey
  ) {
    return
  }
  const dialog = event.currentTarget
  const controls = Array.from(
    dialog.querySelectorAll<HTMLElement>(
      'a[href], button, input, select, textarea, [tabindex]',
    ),
  ).filter(
    (element) =>
      element.tabIndex >= 0 &&
      !element.matches(':disabled, [inert], [hidden]') &&
      !element.closest('[inert], [hidden]') &&
      element.getClientRects().length > 0,
  )
  const first = controls[0]
  const last = controls[controls.length - 1]
  if (!first || !last) {
    event.preventDefault()
    return
  }
  const active = document.activeElement
  if (event.shiftKey && (active === first || active === dialog)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || active === dialog)) {
    event.preventDefault()
    first.focus()
  }
}
