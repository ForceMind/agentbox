import { expect, type Locator, type Page } from '@playwright/test'

import type { Rc9Locale } from './rc9-fixtures'

/** Assert the locale selected for the browser document, never catalog copy. */
export async function assertRc9DocumentLocale(
  page: Page,
  locale: Rc9Locale,
): Promise<void> {
  await expect(page.locator('html')).toHaveAttribute('lang', locale)
}

/**
 * Callers provide route-owned title copy. This module deliberately never reads
 * the i18n catalog, so the browser assertion cannot mirror production text.
 */
export async function assertRc9Title(
  page: Page,
  expectedTitle: string | RegExp,
): Promise<void> {
  await expect(page).toHaveTitle(expectedTitle)
}

export async function assertRc9NonEmptyTitle(page: Page): Promise<void> {
  await expect
    .poll(() => page.title().then((title) => title.trim().length))
    .toBeGreaterThan(0)
}

export async function assertRc9NoHorizontalOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    documentClientWidth: document.documentElement.clientWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
    bodyClientWidth: document.body.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
  }))
  expect(
    dimensions.documentScrollWidth,
    `document overflow: ${JSON.stringify(dimensions)}`,
  ).toBeLessThanOrEqual(dimensions.documentClientWidth)
  expect(
    dimensions.bodyScrollWidth,
    `body overflow: ${JSON.stringify(dimensions)}`,
  ).toBeLessThanOrEqual(dimensions.bodyClientWidth)
}

export async function assertRc9InteractiveTargets(
  page: Page,
  minimumPixels = 44,
): Promise<void> {
  const targets = page.locator(
    'button:visible, a[href]:visible, input:not([type="hidden"]):visible, select:visible, textarea:visible, summary:visible',
  )
  const count = await targets.count()
  expect(count, 'expected at least one interactive target').toBeGreaterThan(0)
  for (let index = 0; index < count; index += 1) {
    const target = targets.nth(index)
    await expect(target).toBeVisible()
    const box = await target.boundingBox()
    expect(box, `target ${index} has no bounding box`).not.toBeNull()
    expect(box?.width, `target ${index} is too narrow`).toBeGreaterThanOrEqual(
      minimumPixels,
    )
    expect(box?.height, `target ${index} is too short`).toBeGreaterThanOrEqual(
      minimumPixels,
    )
  }
}

type Rc9FocusStyle = {
  outlineStyle: string
  outlineWidth: string
  outlineColor: string
  outlineOffset: string
  boxShadow: string
}

function focusStyle(element: Element): Rc9FocusStyle {
  const style = getComputedStyle(element)
  return {
    outlineStyle: style.outlineStyle,
    outlineWidth: style.outlineWidth,
    outlineColor: style.outlineColor,
    outlineOffset: style.outlineOffset,
    boxShadow: style.boxShadow,
  }
}

/**
 * Focus must visibly change the requested target's treatment. A static box
 * shadow is not accepted as focus evidence because before/after styles are
 * compared directly.
 */
export async function assertRc9Focus(target: Locator): Promise<void> {
  await target.evaluate(() => {
    if (document.activeElement instanceof HTMLElement)
      document.activeElement.blur()
  })
  const before = await target.evaluate(focusStyle)
  await target.focus()
  await expect(target).toBeFocused()
  const after = await target.evaluate(focusStyle)
  const changed = Object.keys(after).some(
    (key) =>
      after[key as keyof Rc9FocusStyle] !== before[key as keyof Rc9FocusStyle],
  )
  expect(changed, 'focus did not change the target presentation').toBe(true)
}

/** A modal must own focus while visible; route tests assert restoration on close. */
export async function assertRc9ModalDialog(
  page: Page,
  dialog: Locator,
): Promise<void> {
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveAttribute('role', /^(dialog|alertdialog)$/)
  await expect(dialog).toHaveAttribute('aria-modal', 'true')
  await expect
    .poll(() =>
      dialog.evaluate((element) => element.contains(document.activeElement)),
    )
    .toBe(true)
  await assertRc9NoHorizontalOverflow(page)
}

export async function assertRc9FocusRestored(target: Locator): Promise<void> {
  await expect(target).toBeFocused()
}

/**
 * Technical identifiers remain printable ASCII, LTR English and excluded from
 * browser translation even when their surrounding document is Chinese.
 */
export async function assertRc9TechnicalRendering(
  technical: Locator,
): Promise<void> {
  await expect(technical).toHaveAttribute('lang', 'en')
  await expect(technical).toHaveAttribute('dir', 'ltr')
  await expect(technical).toHaveAttribute('translate', 'no')
  const text = await technical.textContent()
  expect(text ?? '', 'technical value must be printable ASCII').toMatch(
    /^[\x20-\x7e]+$/,
  )
}

type Rc9CanarySurfaces = {
  outerHTML: boolean
  elementAttributes: boolean
  formValues: boolean
  localStorage: boolean
  sessionStorage: boolean
  location: boolean
  title: boolean
  historyState: boolean
  windowName: boolean
}

/**
 * Scans browser surfaces which may survive a route/state transition, including
 * complete markup, attributes and live form values. The canary must be a
 * synthetic, non-secret value; artifact recording is disabled in the Playwright
 * configuration and every sensitive spec repeats that setting.
 */
export async function assertRc9CanaryAbsent(
  page: Page,
  canary: string,
): Promise<void> {
  if (!canary) throw new Error('rc9 canary must be non-empty')
  const surfaces = await page.evaluate((value): Rc9CanarySurfaces => {
    const storageContains = (storage: Storage) =>
      Array.from({ length: storage.length }, (_, index) => index).some(
        (index) => {
          const key = storage.key(index)
          return (
            key?.includes(value) || storage.getItem(key ?? '')?.includes(value)
          )
        },
      )
    const stateContains = (
      state: unknown,
      seen = new WeakSet<object>(),
    ): boolean => {
      if (typeof state === 'string') return state.includes(value)
      if (state === null || typeof state !== 'object') return false
      if (seen.has(state)) return false
      seen.add(state)
      try {
        if (state instanceof Map) {
          return Array.from(state).some(
            ([key, entry]) =>
              stateContains(key, seen) || stateContains(entry, seen),
          )
        }
        if (state instanceof Set) {
          return Array.from(state).some((entry) => stateContains(entry, seen))
        }
        return Object.getOwnPropertyNames(state).some((key) => {
          if (key.includes(value)) return true
          const descriptor = Object.getOwnPropertyDescriptor(state, key)
          if (descriptor === undefined || !('value' in descriptor)) return true
          return stateContains(descriptor.value, seen)
        })
      } catch {
        // History is normally structured-clone data. If it becomes opaque, the
        // assertion must fail closed rather than silently miss a retained value.
        return true
      }
    }
    const elementAttributes = Array.from(document.querySelectorAll('*')).some(
      (element) =>
        Array.from(element.attributes).some(
          (attribute) =>
            attribute.name.includes(value) || attribute.value.includes(value),
        ),
    )
    const controlValues = Array.from(
      document.querySelectorAll<
        HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >('input, select, textarea'),
    ).some((element) => element.value.includes(value))
    const formValues =
      controlValues ||
      Array.from(document.forms).some((form) => {
        return Array.from(form.elements).some((element) => {
          if (!(
            element instanceof HTMLInputElement ||
            element instanceof HTMLSelectElement ||
            element instanceof HTMLTextAreaElement ||
            element instanceof HTMLOutputElement
          )) {
            return false
          }
          return element.value.includes(value)
        })
      })
    return {
      outerHTML: document.documentElement.outerHTML.includes(value),
      elementAttributes,
      formValues,
      localStorage: storageContains(localStorage),
      sessionStorage: storageContains(sessionStorage),
      location: location.href.includes(value),
      title: document.title.includes(value),
      historyState: stateContains(history.state),
      windowName: window.name.includes(value),
    }
  }, canary)
  expect(surfaces).toEqual({
    outerHTML: false,
    elementAttributes: false,
    formValues: false,
    localStorage: false,
    sessionStorage: false,
    location: false,
    title: false,
    historyState: false,
    windowName: false,
  })
}
