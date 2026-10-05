import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { expect, test as base } from '@playwright/test'
import { startA3NativeFixture, type StaticMode } from './a3NativeFixture'

type Fixture = Awaited<ReturnType<typeof startA3NativeFixture>>
const test = base.extend<{ native: Fixture }>({
  native: async ({ browserName }, deliverFixture, testInfo) => {
    if (browserName !== 'chromium')
      throw new Error('native A3 fixture requires CI Chromium')
    const fixture = await startA3NativeFixture(testInfo)
    try {
      await deliverFixture(fixture)
    } finally {
      await fixture.close()
    }
  },
})
test.use({ screenshot: 'off', trace: 'off', video: 'off' })
test.setTimeout(60_000)
const projectId = `prj_${'a'.repeat(32)}`
type Status = {
  active: number
  active_bundles: number
  burned_nonces: number
  diff_count: number
  held: boolean
  bundles: number
  observed_api_pids: number[]
}
async function status(fixture: Fixture) {
  return (await fixture.call('status')) as Status
}
async function open(fixture: Fixture) {
  const { page, origin } = fixture
  await page.goto(`${origin}/login`)
  await page.getByLabel('用户名', { exact: true }).fill('native-fixture')
  await page
    .getByLabel('密码', { exact: true })
    .fill('published synthetic native fixture password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(`${origin}/dashboard`)
  await page.goto(`${origin}/projects/${projectId}/changes`)
  await expect(
    page.getByRole('button', { name: '读取暂存补丁：success.txt' }),
  ).toBeVisible()
}
const button = (fixture: Fixture) =>
  fixture.page.getByRole('button', { name: '读取暂存补丁：success.txt' })
const patch = (fixture: Fixture) =>
  fixture.page.getByTestId('a3-complete-patch')
const noPatch = (fixture: Fixture) => expect(patch(fixture)).toHaveCount(0)
async function read(fixture: Fixture) {
  await expect(button(fixture)).toBeEnabled()
  await button(fixture).click()
}

test('formal App login → independent HTTPS trust → separate native Runtime → complete inert Chinese Changes', async ({
  native,
}, testInfo) => {
  await open(native)
  await expect(button(native)).toBeEnabled()
  expect(native.proof.api_pid).not.toBe(native.proof.runtime_pid)
  expect(native.proof.api_a3_runtime_imports).toBe(0)
  expect(native.proof.isolated).toBe(true)
  expect(native.proof.api_uid).toBe(61131)
  expect(native.proof.static_owner_uid).toBe(0)
  expect(native.proof.api_cannot_write_static).toBe(true)
  expect(native.proof.api_cannot_read_patch).toBe(true)
  expect(native.counts.bootstrap).toBeGreaterThanOrEqual(2)
  expect(native.counts.observations).toBe(0)
  expect(native.counts.websockets).toBe(0)
  expect((await status(native)).diff_count).toBe(0)
  await button(native).focus()
  await button(native).press('Enter')
  await expect(patch(native)).toContainText('A3 native complete diff')
  await expect(patch(native)).toContainText(
    '<img src=x onerror=window.a3Executed=true>',
  )
  await expect(patch(native)).toContainText('🌍')
  await expect(patch(native)).not.toContainText('unstaged-exclusion-canary')
  expect(await patch(native).locator('img,script,svg,a').count()).toBe(0)
  expect(
    await native.page.evaluate(
      () => (window as Window & { a3Executed?: boolean }).a3Executed,
    ),
  ).toBeUndefined()
  expect((await patch(native).textContent())!.length).toBeGreaterThan(24_000)
  expect(native.counts.observations).toBe(1)
  expect(native.counts.websockets).toBe(1)
  const completed = await status(native)
  expect(completed.active).toBe(1)
  expect(completed.active_bundles).toBe(1)
  expect(completed.burned_nonces).toBe(1)
  expect(completed.observed_api_pids).toEqual([native.proof.api_pid])
  expect(
    await native.page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    ),
  ).toBe(false)
  await patch(native).focus()
  await expect(patch(native)).toBeFocused()
  await mkdir(resolve('test-results'), { recursive: true })
  await native.page.screenshot({
    path: resolve(
      'test-results',
      `a3-native-changes-${testInfo.project.name}.png`,
    ),
    fullPage: true,
  })
  await native.page.getByRole('button', { name: '清除内容' }).click()
  await noPatch(native)
  await expect.poll(async () => (await status(native)).active).toBe(0)
  await read(native)
  await expect(patch(native)).toBeVisible()
  expect(native.counts.observations).toBe(2)
  expect((await status(native)).burned_nonces).toBe(2)
})

for (const mode of [
  'missing-markers',
  'missing',
  'malformed',
  'oversize',
  'redirect',
  'mismatch',
  'wrong-origin',
  'expired',
] satisfies StaticMode[]) {
  test(`independent static ${mode} refuses observations and sockets`, async ({
    native,
  }) => {
    native.setStaticMode(mode)
    await open(native)
    await expect(button(native)).toBeDisabled()
    await expect(native.page.getByTestId('a3-reader-status')).toContainText(
      '暂存内容暂不可用',
    )
    expect(native.counts.observations).toBe(0)
    expect(native.counts.websockets).toBe(0)
    if (mode === 'missing-markers') expect(native.counts.bootstrap).toBe(0)
    else await expect.poll(() => native.counts.bootstrap).toBeGreaterThan(0)
    expect((await status(native)).diff_count).toBe(0)
  })
}

for (const [filename, message] of [
  ['binary.bin', '二进制文件'],
  ['large.txt', '超出完整读取上限'],
  ['.env', '暂存内容暂不可用'],
] as const) {
  test(`formal route ${filename} has bounded actionable Chinese state`, async ({
    native,
  }) => {
    await open(native)
    await expect(button(native)).toBeEnabled()
    await native.page
      .getByRole('button', { name: `读取暂存补丁：${filename}` })
      .click()
    await expect(native.page.getByTestId('a3-reader-status')).toContainText(
      message,
    )
    await noPatch(native)
    await expect.poll(async () => (await status(native)).active).toBe(0)
  })
}

test('cancel before native END fences delayed publication and refresh does not replay', async ({
  native,
}) => {
  await open(native)
  await native.call('mode', { payload: { value: 'hold-end' } })
  await read(native)
  await expect.poll(async () => (await status(native)).held).toBe(true)
  await noPatch(native)
  await native.page.getByRole('button', { name: '取消读取' }).click()
  await native.call('release')
  await expect.poll(async () => (await status(native)).active).toBe(0)
  await noPatch(native)
  await native.page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(button(native)).toBeEnabled()
  expect(native.counts.observations).toBe(1)
  expect(native.counts.websockets).toBe(1)
  expect((await status(native)).burned_nonces).toBe(1)
})

test('tampered native END never reaches complete DOM', async ({ native }) => {
  await open(native)
  await native.call('mode', { payload: { value: 'tamper-end' } })
  await read(native)
  await expect(native.page.getByTestId('a3-reader-status')).toContainText(
    '验证或连接失败',
  )
  await noPatch(native)
  await expect.poll(async () => (await status(native)).active).toBe(0)
})

for (const change of [
  'revoke',
  'auth-epoch',
  'project',
  'epoch',
  'peer',
  'lifecycle',
]) {
  test(`completed native display clears after ${change} without replay`, async ({
    native,
  }) => {
    await open(native)
    await read(native)
    await expect(patch(native)).toBeVisible()
    await native.call(change)
    await noPatch(native)
    await expect.poll(async () => (await status(native)).active).toBe(0)
    expect(native.counts.observations).toBe(1)
    expect(native.counts.websockets).toBe(1)
  })
}

test('API suspension expires displayed observed freshness and resume cannot revive it', async ({
  native,
}) => {
  await open(native)
  await read(native)
  await expect(patch(native)).toBeVisible()
  await native.call('pause-api')
  try {
    await expect(patch(native)).toHaveCount(0, { timeout: 2000 })
  } finally {
    await native.call('resume-api')
  }
  await expect.poll(async () => (await status(native)).active).toBe(0)
  await noPatch(native)
  expect(native.counts.observations).toBe(1)
  expect(native.counts.websockets).toBe(1)
})

test('independent bootstrap rotation invalidates completed content', async ({
  native,
}) => {
  await open(native)
  await read(native)
  await expect(patch(native)).toBeVisible()
  native.setStaticMode('changed')
  await expect(patch(native)).toHaveCount(0, { timeout: 7000 })
  await expect.poll(async () => (await status(native)).active).toBe(0)
  expect(native.counts.observations).toBe(1)
})

for (const event of ['pagehide', 'freeze', 'offline']) {
  test(`${event} clears native displayed owner without automatic read`, async ({
    native,
  }) => {
    await open(native)
    await read(native)
    await expect(patch(native)).toBeVisible()
    await native.page.evaluate((name) => {
      const target = name === 'freeze' ? document : window
      target.dispatchEvent(new Event(name))
    }, event)
    await noPatch(native)
    await expect.poll(async () => (await status(native)).active).toBe(0)
    expect(native.counts.observations).toBe(1)
    expect(native.counts.websockets).toBe(1)
  })
}

test('formal route departure and browser Back never resurrect completed content', async ({
  native,
}) => {
  await open(native)
  await read(native)
  await expect(patch(native)).toBeVisible()
  await native.page.goto(`${native.origin}/dashboard`)
  await native.page.goBack()
  await expect(button(native)).toBeEnabled()
  await noPatch(native)
  await expect.poll(async () => (await status(native)).active).toBe(0)
  expect(native.counts.observations).toBe(1)
  expect(native.counts.websockets).toBe(1)
})
