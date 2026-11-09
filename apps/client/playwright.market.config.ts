import { defineConfig } from '@playwright/test'

// One isolated synthetic service; never the user's port 8000 or saved credentials.
export default defineConfig({
  testDir: './tests/browser', testMatch: 'simulated-market.spec.ts', workers: 1,
  outputDir: '../../.local/playwright-market-results',
  reporter: [['list'], ['json', { outputFile: '../../.local/logs/simulated-market/browser-results.json' }]],
  use: { baseURL: 'http://127.0.0.1:18006', channel: 'msedge', actionTimeout: 10000, viewport: { width: 1366, height: 900 }, trace: 'off' },
  webServer: { command: '\"../../.venv/Scripts/python.exe\" \"../../tests/fixtures/s2_model_server.py\" --port 18006', url: 'http://127.0.0.1:18006/healthz', reuseExistingServer: false, timeout: 30000 },
})
