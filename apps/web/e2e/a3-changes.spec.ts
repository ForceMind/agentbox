import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { installA3Fixture } from './a3FixtureBridge'

test.use({ screenshot: 'off', trace: 'off', video: 'off' })
const projectId = `prj_${'a'.repeat(32)}`
type Fixture = Awaited<ReturnType<typeof installA3Fixture>>
type Status = {
  diff_count: number
  active: number
  burned_nonces: number
  held: boolean
  observations: number
}
async function status(fixture: Fixture) {
  return (await fixture.call('status')) as Status
}
async function open(page: Page, baseURL: string | undefined, suffix = '') {
  const fixture = await installA3Fixture(page)
  await page.route(
    `**/api/v1/projects/${projectId}/git/changes*`,
    async (route) => {
      await route.fulfill({ status: 200, json: await fixture.call('metadata') })
    },
  )
  await page.goto(
    `${process.env.PLAYWRIGHT_HARNESS_BASE_URL ?? baseURL}/e2e/a3-changes-harness.html${suffix}`,
  )
  await expect(
    page.getByRole('button', { name: '读取暂存补丁：success.txt' }),
  ).toBeVisible()
  return fixture
}
const readSuccess = (page: Page) =>
  page.getByRole('button', { name: '读取暂存补丁：success.txt' }).click()
const noPatch = (page: Page) =>
  expect(page.getByTestId('a3-complete-patch')).toHaveCount(0)

test('native Git → authenticated bootstrap → actual crypto → inert complete Changes DOM', async ({
  page,
  baseURL,
}, testInfo) => {
  const fixture = await open(page, baseURL)
  try {
    const before = await status(fixture)
    expect(before.diff_count).toBe(0)
    expect(before.observations).toBe(0)
    const button = page.getByRole('button', {
      name: '读取暂存补丁：success.txt',
    })
    await button.focus()
    await expect(button).toBeFocused()
    expect((await status(fixture)).diff_count).toBe(0)
    await button.press('Enter')
    const patch = page.getByTestId('a3-complete-patch')
    await expect(patch).toContainText('A3 synthetic complete diff')
    await expect(patch).toContainText(
      '<img src=x onerror=window.a3Executed=true>',
    )
    await expect(patch).toContainText('🌍')
    await expect(patch).not.toContainText('unstaged-exclusion-canary')
    expect(await patch.locator('img,script,a,svg').count()).toBe(0)
    expect(
      await page.evaluate(
        () => (window as Window & { a3Executed?: boolean }).a3Executed,
      ),
    ).toBeUndefined()
    expect((await patch.textContent())!.length).toBeGreaterThan(24_000)
    expect((await status(fixture)).diff_count).toBeGreaterThan(0)
    expect((await status(fixture)).observations).toBe(1)
    expect((await status(fixture)).burned_nonces).toBe(1)
    await expect(
      page.getByRole('button', { name: '读取暂存补丁：unstaged-only.txt' }),
    ).toHaveCount(0)
    await patch.focus()
    await expect(patch).toBeFocused()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    )
    expect(overflow).toBe(false)
    // Explicit synthetic Changes-only screenshots; global screenshots/traces stay off.
    await mkdir(resolve('test-results'), { recursive: true })
    await page.screenshot({
      path: resolve('test-results', `a3-changes-${testInfo.project.name}.png`),
      fullPage: true,
    })
    await page.getByRole('button', { name: '清除内容' }).click()
    await noPatch(page)
    await readSuccess(page)
    await expect(patch).toBeVisible()
    expect((await status(fixture)).observations).toBe(2)
    expect((await status(fixture)).burned_nonces).toBe(2)
  } finally {
    await fixture.close()
  }
})

test('cancel fences delayed END and refresh cannot replay a read', async ({
  page,
  baseURL,
}) => {
  const fixture = await open(page, baseURL)
  try {
    await fixture.call('mode', { value: 'hold-end' })
    await readSuccess(page)
    await expect.poll(async () => (await status(fixture)).held).toBe(true)
    await noPatch(page)
    await page.getByRole('button', { name: '取消读取' }).click()
    await expect(page.getByTestId('a3-reader-status')).toContainText('尚未读取')
    await fixture.call('release')
    await expect.poll(async () => (await status(fixture)).active).toBe(0)
    await noPatch(page)
    const refreshed = page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${projectId}/git/changes`,
    )
    await page.getByRole('button', { name: '刷新', exact: true }).click()
    const metadataResponse = await refreshed
    expect(metadataResponse.status()).toBe(200)
    expect(await metadataResponse.finished()).toBeNull()
    await expect(
      page.getByRole('button', { name: '读取暂存补丁：success.txt' }),
    ).toBeVisible()
    await noPatch(page)
    expect((await status(fixture)).observations).toBe(1)
  } finally {
    await fixture.close()
  }
})

for (const mode of ['tamper', 'drop-page'] as const) {
  test(`${mode} never publishes partial or unverified source`, async ({
    page,
    baseURL,
  }) => {
    const fixture = await open(page, baseURL)
    try {
      await fixture.call('mode', { value: mode })
      await readSuccess(page)
      await expect(page.getByTestId('a3-reader-status')).toContainText(
        '验证或连接失败',
      )
      await noPatch(page)
      await expect.poll(async () => (await status(fixture)).active).toBe(0)
    } finally {
      await fixture.close()
    }
  })
}
for (const [filename, message] of [
  ['binary.bin', '二进制文件'],
  ['large.txt', '超出完整读取上限'],
  ['.env', '暂存内容暂不可用'],
] as const) {
  test(`${filename} shows its actionable bounded Chinese state`, async ({
    page,
    baseURL,
  }) => {
    const fixture = await open(page, baseURL)
    try {
      await page
        .getByRole('button', { name: `读取暂存补丁：${filename}` })
        .click()
      await expect(page.getByTestId('a3-reader-status')).toContainText(message)
      await noPatch(page)
    } finally {
      await fixture.close()
    }
  })
}
for (const event of [
  'a3-test-trust-revoke',
  'visibilitychange',
  'pagehide',
  'freeze',
] as const) {
  test(`${event} clears completed content without automatic replay`, async ({
    page,
    baseURL,
  }) => {
    const fixture = await open(page, baseURL)
    try {
      await readSuccess(page)
      await expect(page.getByTestId('a3-complete-patch')).toBeVisible()
      await page.evaluate((event) => {
        if (event === 'visibilitychange')
          Object.defineProperty(document, 'hidden', {
            configurable: true,
            value: true,
          })
        const target =
          event === 'visibilitychange' || event === 'freeze' ? document : window
        target.dispatchEvent(new Event(event))
      }, event)
      await noPatch(page)
      await expect(page.getByTestId('a3-reader-status')).toContainText(
        event === 'a3-test-trust-revoke' ? '读取权限' : '已失效',
      )
      expect((await status(fixture)).observations).toBe(1)
    } finally {
      await fixture.close()
    }
  })
}
test('API permission loss is bounded and cannot read content', async ({
  page,
  baseURL,
}) => {
  const fixture = await open(page, baseURL)
  try {
    await fixture.call('mode', { value: 'permission' })
    await readSuccess(page)
    await expect(page.getByTestId('a3-reader-status')).toContainText('读取权限')
    await noPatch(page)
    expect((await status(fixture)).diff_count).toBe(0)
  } finally {
    await fixture.close()
  }
})
for (const missing of ['adapter', 'pin']) {
  test(`missing ${missing} does not obtain selectors or content`, async ({
    page,
    baseURL,
  }) => {
    const fixture = await open(page, baseURL, `?missing=${missing}`)
    try {
      await expect(
        page.getByRole('button', { name: '读取暂存补丁：success.txt' }),
      ).toBeDisabled()
      await expect(page.getByTestId('a3-reader-status')).toContainText(
        '暂存内容暂不可用',
      )
      expect((await status(fixture)).observations).toBe(0)
      expect((await status(fixture)).diff_count).toBe(0)
    } finally {
      await fixture.close()
    }
  })
}
