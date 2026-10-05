/// <reference lib="es2021.promise" />
/// <reference lib="es2022.error" />
/** Test-only cleanup ordering and failure preservation; no browser dependencies. */
export async function runFixtureCleanup(steps: Array<() => Promise<void>>) {
  const failures: unknown[] = []
  for (const step of steps) {
    try {
      await step()
    } catch (error) {
      failures.push(error)
    }
  }
  if (failures.length)
    throw new AggregateError(failures, 'A3 fixture cleanup failed')
}

export async function preserveFixtureFailure<T>(
  operation: () => Promise<T>,
  cleanup: () => Promise<void>,
): Promise<T> {
  try {
    return await operation()
  } catch (primary) {
    try {
      await cleanup()
    } catch (secondary) {
      // Playwright shows the cause plus both aggregate members. Keep the original
      // setup/browser error first; a teardown EACCES must never replace it again.
      const message =
        primary instanceof Error ? primary.message : 'unknown failure'
      throw new AggregateError(
        [primary, secondary],
        `A3 fixture failed before cleanup: ${message}`,
        { cause: primary },
      )
    }
    throw primary
  }
}
