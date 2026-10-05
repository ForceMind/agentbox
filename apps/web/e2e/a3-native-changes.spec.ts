import { createHash } from 'node:crypto'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { expect, test as base } from '@playwright/test'
import { startA3NativeFixture, type StaticMode } from './a3NativeFixture'
import { a3FixtureStatusNumbers } from './a3NativeCounters'

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
test.afterEach(async ({ native }, testInfo) => {
  if (
    testInfo.status === testInfo.expectedStatus ||
    testInfo.status === 'skipped'
  )
    return
  // Playwright runs afterEach before test-scoped fixture teardown. Read status
  // only; the runner keeps the original body error and retries independently.
  try {
    const counters = native.socketCounters.snapshot()
    let fixture = a3FixtureStatusNumbers(undefined)
    try {
      fixture = a3FixtureStatusNumbers(await native.call('runtime-status'))
    } catch {
      // Missing diagnostics are -1, never exception values or guessed counts.
    }
    console.info('A3_NATIVE_COUNTS ' + JSON.stringify({ counters, fixture }))
  } catch {
    // Diagnostic work must not add an error or prevent the original teardown.
  }
})
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
async function read(fixture: Fixture, filename = 'success.txt') {
  const selected = fixture.page.getByRole('button', {
    name: `读取暂存补丁：${filename}`,
    exact: true,
  })
  await expect(selected).toBeEnabled()
  await selected.click()
}
const unified = (fixture: Fixture) =>
  fixture.page.getByTestId('unified-diff-table')
const viewButton = (fixture: Fixture, name: '统一视图' | '原文') =>
  fixture.page.getByRole('button', { name, exact: true })
const successSource =
  'A3 native complete diff\n<img src=x onerror=window.a3Executed=true>\n' +
  '<a href="https://example.invalid/a3">inert link</a>\n' +
  '<script>window.a3Executed=true</script>\n' +
  `${'x'.repeat(6000)}\n`.repeat(4) +
  '🌍\n'
const longLineSource = `long-line raw fallback\n${'L'.repeat(9000)}\n完整末尾 🌍\n`
function blobOid(source: string) {
  return createHash('sha1')
    .update(`blob ${Buffer.byteLength(source)}\0`)
    .update(source)
    .digest('hex')
}
function addedPatch(filename: string, source: string) {
  const lines = source.slice(0, -1).split('\n')
  return [
    `diff --git a/${filename} b/${filename}`,
    'new file mode 100644',
    `index ${'0'.repeat(40)}..${blobOid(source)}`,
    '--- /dev/null',
    `+++ b/${filename}`,
    `@@ -0,0 +1,${lines.length} @@`,
    ...lines.map((line) => `+${line}`),
    '',
  ].join('\n')
}
type DiffRow = readonly [
  kind: 'added' | 'deleted' | 'context' | 'marker',
  oldLine: string,
  newLine: string,
  source: string,
]
async function expectUnifiedRows(
  fixture: Fixture,
  expected: readonly DiffRow[],
) {
  await expect(unified(fixture)).toBeVisible()
  await expect(viewButton(fixture, '统一视图')).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  const rows = await unified(fixture)
    .locator(
      'tr[data-kind="added"],tr[data-kind="deleted"],tr[data-kind="context"],tr[data-kind="marker"]',
    )
    .evaluateAll((elements) =>
      elements.map((row) => [
        row.getAttribute('data-kind'),
        row.querySelector('[data-testid="diff-old-line"]')?.textContent ?? '',
        row.querySelector('[data-testid="diff-new-line"]')?.textContent ?? '',
        row.querySelector('[data-testid="diff-line-text"]')?.textContent ?? '',
      ]),
    )
  expect(rows).toEqual(expected)
}
async function expectNoPageOverflow(fixture: Fixture) {
  expect(
    await fixture.page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    ),
  ).toBe(false)
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
  await expectUnifiedRows(
    native,
    successSource
      .slice(0, -1)
      .split('\n')
      .map((line, index): DiffRow => [
        'added',
        '',
        String(index + 1),
        `+${line}`,
      ]),
  )
  const wrap = native.page.getByRole('checkbox', {
    name: '换行显示',
    exact: true,
  })
  await expect(wrap).toBeChecked()
  await expectNoPageOverflow(native)
  const beforeViewSwitch = await status(native)
  // Original source is exact and complete, not table line numbers or a clipped preview.
  for (let iteration = 0; iteration < 3; iteration += 1) {
    if (iteration === 0) {
      await viewButton(native, '原文').focus()
      await expect(viewButton(native, '原文')).toBeFocused()
      await viewButton(native, '原文').press('Enter')
    } else await viewButton(native, '原文').click()
    await expect(viewButton(native, '原文')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(unified(native)).toHaveCount(0)
    expect(await patch(native).textContent()).toBe(
      addedPatch('success.txt', successSource),
    )
    expect((await patch(native).textContent())!.length).toBeGreaterThan(24_000)
    if (iteration === 0) {
      await viewButton(native, '统一视图').focus()
      await expect(viewButton(native, '统一视图')).toBeFocused()
      await viewButton(native, '统一视图').press('Space')
    } else await viewButton(native, '统一视图').click()
    await expect(unified(native)).toBeVisible()
  }
  await wrap.focus()
  await expect(wrap).toBeFocused()
  await wrap.press('Space')
  await expect(wrap).not.toBeChecked()
  await expectNoPageOverflow(native)
  expect(
    await patch(native).evaluate(
      (element) => element.scrollWidth > element.clientWidth,
    ),
  ).toBe(true)
  await patch(native).focus()
  await expect(patch(native)).toBeFocused()
  await patch(native).press('ArrowRight')
  await expect
    .poll(() => patch(native).evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0)
  await wrap.focus()
  await expect(wrap).toBeFocused()
  await wrap.press('Space')
  await expect(wrap).toBeChecked()
  await expectNoPageOverflow(native)
  expect(
    await patch(native).evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBe(true)
  const afterViewSwitch = await status(native)
  expect(afterViewSwitch.diff_count).toBe(beforeViewSwitch.diff_count)
  expect(afterViewSwitch.burned_nonces).toBe(beforeViewSwitch.burned_nonces)
  expect(native.counts.observations).toBe(1)
  expect(native.counts.websockets).toBe(1)
  const completed = await status(native)
  expect(completed.active).toBe(1)
  expect(completed.active_bundles).toBe(1)
  expect(completed.burned_nonces).toBe(1)
  expect(completed.observed_api_pids).toEqual([native.proof.api_pid])
  await expectNoPageOverflow(native)
  await patch(native).focus()
  await expect(patch(native)).toBeFocused()
  await mkdir(resolve('test-results'), { recursive: true })
  await native.page.evaluate(() =>
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' }),
  )
  await expect
    .poll(() => native.page.evaluate(() => [window.scrollX, window.scrollY]))
    .toEqual([0, 0])
  await expect(patch(native)).toBeFocused()
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
  await expect(unified(native)).toBeVisible()
  expect(native.counts.observations).toBe(2)
  expect((await status(native)).burned_nonces).toBe(2)
})

const structuredCases: {
  filename: string
  before: string
  after: string | null
  body: string
  rows: DiffRow[]
  hunks: string[]
}[] = [
  {
    filename: 'modify.txt',
    before: '上下文 α\nold value\n尾部 Ω\n',
    after: '上下文 α\nnew value 🌍\n尾部 Ω\n',
    body: '@@ -1,3 +1,3 @@\n 上下文 α\n-old value\n+new value 🌍\n 尾部 Ω\n',
    rows: [
      ['context', '1', '1', ' 上下文 α'],
      ['deleted', '2', '', '-old value'],
      ['added', '', '2', '+new value 🌍'],
      ['context', '3', '3', ' 尾部 Ω'],
    ],
    hunks: ['@@ -1,3 +1,3 @@'],
  },
  {
    filename: 'delete.txt',
    before: 'removed first\n删除第二行 🌍\n',
    after: null,
    body: '@@ -1,2 +0,0 @@\n-removed first\n-删除第二行 🌍\n',
    rows: [
      ['deleted', '1', '', '-removed first'],
      ['deleted', '2', '', '-删除第二行 🌍'],
    ],
    hunks: ['@@ -1,2 +0,0 @@'],
  },
  {
    filename: 'multiple-hunks.txt',
    before: Array.from(
      { length: 30 },
      (_, index) => `context ${String(index + 1).padStart(2, '0')}\n`,
    ).join(''),
    after: Array.from({ length: 30 }, (_, index) =>
      index === 1
        ? 'first changed 🌍\n'
        : index === 28
          ? 'last changed 中文\n'
          : `context ${String(index + 1).padStart(2, '0')}\n`,
    ).join(''),
    body: '@@ -1,5 +1,5 @@\n context 01\n-context 02\n+first changed 🌍\n context 03\n context 04\n context 05\n@@ -26,5 +26,5 @@ context 25\n context 26\n context 27\n context 28\n-context 29\n+last changed 中文\n context 30\n',
    rows: [
      ['context', '1', '1', ' context 01'],
      ['deleted', '2', '', '-context 02'],
      ['added', '', '2', '+first changed 🌍'],
      ['context', '3', '3', ' context 03'],
      ['context', '4', '4', ' context 04'],
      ['context', '5', '5', ' context 05'],
      ['context', '26', '26', ' context 26'],
      ['context', '27', '27', ' context 27'],
      ['context', '28', '28', ' context 28'],
      ['deleted', '29', '', '-context 29'],
      ['added', '', '29', '+last changed 中文'],
      ['context', '30', '30', ' context 30'],
    ],
    hunks: ['@@ -1,5 +1,5 @@', '@@ -26,5 +26,5 @@ context 25'],
  },
  {
    filename: 'crlf.txt',
    before: 'CRLF context\r\nold CRLF\r\nCRLF tail\r\n',
    after: 'CRLF context\r\nnew CRLF\r\nCRLF tail\r\n',
    body: '@@ -1,3 +1,3 @@\n CRLF context\r\n-old CRLF\r\n+new CRLF\r\n CRLF tail\r\n',
    rows: [
      ['context', '1', '1', ' CRLF context\r'],
      ['deleted', '2', '', '-old CRLF\r'],
      ['added', '', '2', '+new CRLF\r'],
      ['context', '3', '3', ' CRLF tail\r'],
    ],
    hunks: ['@@ -1,3 +1,3 @@'],
  },
  {
    filename: 'no-final-newline.txt',
    before: 'line one\nold tail',
    after: 'line one\n新尾 🌍',
    body: '@@ -1,2 +1,2 @@\n line one\n-old tail\n\\ No newline at end of file\n+新尾 🌍\n\\ No newline at end of file\n',
    rows: [
      ['context', '1', '1', ' line one'],
      ['deleted', '2', '', '-old tail'],
      ['marker', '', '', '\\ No newline at end of file'],
      ['added', '', '2', '+新尾 🌍'],
      ['marker', '', '', '\\ No newline at end of file'],
    ],
    hunks: ['@@ -1,2 +1,2 @@'],
  },
]
for (const sample of structuredCases) {
  test(`formal native ${sample.filename} preserves unified rows, exact source and line numbers`, async ({
    native,
  }, testInfo) => {
    await open(native)
    await read(native, sample.filename)
    await expectUnifiedRows(native, sample.rows)
    for (const hunk of sample.hunks)
      await expect(
        unified(native).getByText(hunk, { exact: true }),
      ).toBeVisible()
    await expect(unified(native).getByText(/^@@ /)).toHaveCount(
      sample.hunks.length,
    )
    await expect(
      native.page.getByRole('checkbox', { name: '换行显示', exact: true }),
    ).toBeChecked()
    await expectNoPageOverflow(native)
    await patch(native).focus()
    await expect(patch(native)).toBeFocused()
    const expected = [
      `diff --git a/${sample.filename} b/${sample.filename}`,
      ...(sample.after === null ? ['deleted file mode 100644'] : []),
      `index ${blobOid(sample.before)}..${sample.after === null ? '0'.repeat(40) : blobOid(sample.after)}${sample.after === null ? '' : ' 100644'}`,
      `--- a/${sample.filename}`,
      sample.after === null ? '+++ /dev/null' : `+++ b/${sample.filename}`,
      sample.body,
    ].join('\n')
    const beforeSwitch = await status(native)
    await viewButton(native, '原文').click()
    expect(await patch(native).textContent()).toBe(expected)
    await viewButton(native, '统一视图').click()
    await expectUnifiedRows(native, sample.rows)
    expect((await status(native)).diff_count).toBe(beforeSwitch.diff_count)
    expect(native.counts.observations).toBe(1)
    expect(native.counts.websockets).toBe(1)
    if (sample.filename === 'multiple-hunks.txt') {
      // Synthetic-only evidence of real context, deleted/added rows and hunk styling.
      await patch(native).focus()
      await expect(patch(native)).toBeFocused()
      await mkdir(resolve('test-results'), { recursive: true })
      await native.page.evaluate(() =>
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' }),
      )
      await expect
        .poll(() =>
          native.page.evaluate(() => [window.scrollX, window.scrollY]),
        )
        .toEqual([0, 0])
      await expect(patch(native)).toBeFocused()
      await native.page.screenshot({
        path: resolve(
          'test-results',
          `a3-native-changes-multiple-hunks-${testInfo.project.name}.png`,
        ),
        fullPage: true,
      })
    }
    await native.page.getByRole('button', { name: '清除内容' }).click()
    await noPatch(native)
    await expect(unified(native)).toHaveCount(0)
    await expect.poll(async () => (await status(native)).active).toBe(0)
  })
}

test('formal native renderer long-line fallback keeps the full exact verified patch', async ({
  native,
}) => {
  await open(native)
  await read(native, 'long-line.txt')
  await expect(patch(native)).toBeVisible()
  await expect(unified(native)).toHaveCount(0)
  expect(await patch(native).textContent()).toBe(
    addedPatch('long-line.txt', longLineSource),
  )
  await expect(patch(native)).toContainText('完整末尾 🌍')
  await expectNoPageOverflow(native)
  expect(native.counts.observations).toBe(1)
  expect(native.counts.websockets).toBe(1)
  await native.page.getByRole('button', { name: '清除内容' }).click()
  await noPatch(native)
  await expect.poll(async () => (await status(native)).active).toBe(0)
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
    await expect(unified(native)).toBeVisible()
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
  await expect(unified(native)).toBeVisible()
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
  await expect(unified(native)).toBeVisible()
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
    await expect(unified(native)).toBeVisible()
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
  await expect(unified(native)).toBeVisible()
  await native.page.goto(`${native.origin}/dashboard`)
  await native.page.goBack()
  await expect(button(native)).toBeEnabled()
  await noPatch(native)
  await expect.poll(async () => (await status(native)).active).toBe(0)
  expect(native.counts.observations).toBe(1)
  expect(native.counts.websockets).toBe(1)
})
