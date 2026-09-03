import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL
if (!baseURL || process.env.AGENTBOX_E2E_AUTH_TIMING !== '1') {
  throw new Error('auth timing requires the isolated E2E harness')
}

export default defineConfig({
  testDir: '.',
  testMatch: 'auth-timing.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  reporter: 'dot',
  outputDir: '../test-results/auth-timing',
  preserveOutput: 'never',
  use: {
    baseURL,
    actionTimeout: 5_000,
    navigationTimeout: 5_000,
    screenshot: 'off',
    trace: 'off',
    video: 'off',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 5'] } },
  ],
})
