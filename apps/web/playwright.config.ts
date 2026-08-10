import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL
if (!baseURL) {
  throw new Error(
    'PLAYWRIGHT_BASE_URL must be provided by the isolated E2E harness',
  )
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL,
    // Pair Codes and Phase 6 pane-output canaries are rendered in the DOM.
    // Retained screenshots or traces could become secret-bearing artifacts.
    screenshot: 'off',
    trace: 'off',
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
      },
    },
    {
      name: 'mobile-chromium',
      use: {
        ...devices['Pixel 5'],
        viewport: { width: 390, height: 844 },
      },
    },
  ],
})
