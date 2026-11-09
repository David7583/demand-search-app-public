import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/browser',
  outputDir: '../../.local/playwright-s2-results',
  reporter: [['list'], ['json', { outputFile: '../../.local/logs/s2-frontend-browser-results.json' }]],
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:18000', channel: 'msedge', trace: 'off' },
  projects: [
    { name: 'desktop-edge', use: { baseURL: 'http://127.0.0.1:18000', viewport: { width: 1366, height: 900 } } },
    { name: 'mobile-viewport-edge', use: { baseURL: 'http://127.0.0.1:18001', ...devices['iPhone 13'], defaultBrowserType: 'chromium', channel: 'msedge' } },
  ],
  // Each viewport and the larger collaboration suite have independent synthetic
  // processes/storage and rate-limit windows; production limits stay unchanged.
  // Keep production session/provider limits intact as the suite grows.
  webServer: (process.env.DSA_VERIFY_DESKTOP === '1' ? [18000, 18002, 18003, 18004, 18005] : [18000, 18001, 18002, 18003, 18004, 18005]).map(port => ({
    command: '\"../../.venv/Scripts/python.exe\" \"../../tests/fixtures/s2_model_server.py\" --port ' + port,
    url: 'http://127.0.0.1:' + port + '/healthz',
    reuseExistingServer: false, timeout: 30000,
  })),
})
