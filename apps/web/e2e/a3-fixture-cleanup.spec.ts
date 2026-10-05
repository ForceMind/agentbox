import { expect, test } from '@playwright/test'
import { preserveFixtureFailure, runFixtureCleanup } from './a3FixtureCleanup'

test('fixture cleanup visits every owned resource and preserves failure order', async () => {
  const order: string[] = []
  const browser = new Error('browser close failed')
  const supervisor = new Error('supervisor cleanup failed')
  const result = await runFixtureCleanup([
    async () => {
      order.push('browser')
      throw browser
    },
    async () => {
      order.push('supervisor')
      throw supervisor
    },
    async () => {
      order.push('exit')
    },
  ]).catch((error: unknown) => error)
  expect(order).toEqual(['browser', 'supervisor', 'exit'])
  expect(result).toBeInstanceOf(AggregateError)
  expect((result as AggregateError).errors).toEqual([browser, supervisor])
})

test('setup failure remains primary when supervisor cleanup also fails', async () => {
  const primary = new Error(
    'native fixture process-start:api:control:ImportError',
  )
  const secondary = new Error('EACCES cleanup')
  const result = await preserveFixtureFailure(
    async () => {
      throw primary
    },
    async () => {
      throw secondary
    },
  ).catch((error: unknown) => error)
  expect(result).toBeInstanceOf(AggregateError)
  expect((result as AggregateError).errors).toEqual([primary, secondary])
  expect((result as AggregateError).cause).toBe(primary)
  expect((result as Error).message).toContain(primary.message)
})

test('successful cleanup rethrows the exact original setup failure', async () => {
  const primary = new Error('original setup failure')
  const result = await preserveFixtureFailure(
    async () => {
      throw primary
    },
    async () => undefined,
  ).catch((error: unknown) => error)
  expect(result).toBe(primary)
})

test('successful setup does not prematurely clean its live owner', async () => {
  let cleaned = false
  expect(
    await preserveFixtureFailure(
      async () => 'owned',
      async () => {
        cleaned = true
      },
    ),
  ).toBe('owned')
  expect(cleaned).toBe(false)
})
