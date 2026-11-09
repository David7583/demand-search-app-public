import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

async function openComposer(page: Page) {
  await page.goto('/')
  await expect(page.locator('.config-return-button')).toBeVisible()
  await page.locator('.config-return-button').click()
  await expect(page.locator('.composer textarea')).toBeEnabled()
}
async function cleanup(context: BrowserContext, id: string | null) {
  if (!id) return
  const session = await context.request.get('/api/v1/session')
  const { csrf_token } = await session.json()
  const deleted = await context.request.delete('/api/v1/conversations/' + id, {
    headers: { 'Content-Type': 'application/json', 'X-DSA-CSRF': csrf_token },
  })
  expect(deleted.ok()).toBeTruthy()
}

for (const rejection of [401, 403]) {
  test('real local middleware: recover ' + rejection + ' once and save original text without reload', async ({ page, context }) => {
    let createdId: string | null = null
    await openComposer(page)
    const original = '  Synthetic session recovery ' + rejection + ' ' + Date.now() + '  '
    await page.locator('.composer textarea').fill(original)
    // Missing cookie reproduces lost in-memory session after restart; a new cookie with
    // the old in-page CSRF token reproduces another tab refreshing the session.
    await context.clearCookies()
    if (rejection === 403) expect((await context.request.get('/api/v1/session')).ok()).toBeTruthy()
    const statuses: number[] = []
    let renewals = 0
    page.on('response', response => {
      if (new URL(response.url()).pathname === '/api/v1/conversations' && response.request().method() === 'POST') statuses.push(response.status())
    })
    page.on('request', request => { if (new URL(request.url()).pathname === '/api/v1/session') renewals++ })
    try {
      const created = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/conversations' && response.status() === 201)
      await page.locator('.submit-button').click()
      createdId = (await (await created).json()).id
      await expect(page.locator('.message-text')).toHaveCount(1)
      await expect(page.locator('.message-text')).toHaveText(original)
      await expect(page.locator('.composer textarea')).toHaveValue('')
      expect(statuses).toEqual([rejection, 201])
      expect(renewals).toBe(1)
      const detail = await (await context.request.get('/api/v1/conversations/' + createdId)).json()
      expect(detail.messages).toHaveLength(1)
      expect(detail.messages[0].content).toBe(original)
      expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0)
    } finally { await cleanup(context, createdId) }
  })
}

test('mock denial only: repeated local-session rejection is bounded and preserves draft', async ({ page }) => {
  await openComposer(page)
  let attempts = 0
  let renewals = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/v1/session') renewals++ })
  await page.route('**/api/v1/conversations', route => {
    if (route.request().method() !== 'POST') return route.continue()
    attempts++
    return route.fulfill({ status: 401, json: { error: { code: 'LOCAL_SESSION_REQUIRED', message: 'Synthetic persistent session rejection' } } })
  })
  const original = 'Synthetic retained draft after bounded recovery'
  await page.locator('.composer textarea').fill(original)
  await page.locator('.submit-button').click()
  await expect(page.locator('.error-box')).toContainText('[LOCAL_SESSION_REQUIRED]')
  await expect(page.locator('.composer textarea')).toHaveValue(original)
  expect(attempts).toBe(2)
  expect(renewals).toBe(1)
})

test('mock failures only: failed bootstrap and non-session failures never replay a mutation', async ({ page }) => {
  await openComposer(page)
  const original = 'Synthetic retained draft after connection error'
  await page.locator('.composer textarea').fill(original)
  const failures = [
    { status: 401, code: 'LOCAL_SESSION_REQUIRED', failedRefresh: true },
    { status: 401, code: 'MODEL_KEY_INVALID', failedRefresh: false },
    { status: 403, code: 'ORIGIN_DENIED', failedRefresh: false },
    { status: 500, code: 'INTERNAL_ERROR', failedRefresh: false },
    { status: 0, code: 'NETWORK_ERROR', failedRefresh: false },
  ]
  for (const failure of failures) {
    let attempts = 0
    let renewals = 0
    await page.route('**/api/v1/session', route => {
      renewals++
      return route.fulfill({ status: 503, json: { error: { code: 'SYNTHETIC_UNAVAILABLE' } } })
    })
    await page.route('**/api/v1/conversations', route => {
      if (route.request().method() !== 'POST') return route.continue()
      attempts++
      if (!failure.status) return route.abort('failed')
      return route.fulfill({ status: failure.status, json: { error: { code: failure.code, message: 'Synthetic rejected operation' } } })
    })
    await page.locator('.submit-button').click()
    await expect(page.locator('.error-box')).toContainText('[' + (failure.failedRefresh ? 'SESSION_UNAVAILABLE' : failure.code) + ']')
    await expect(page.locator('.composer textarea')).toHaveValue(original)
    expect(attempts).toBe(1)
    expect(renewals).toBe(failure.failedRefresh ? 1 : 0)
    await page.unroute('**/api/v1/session')
    await page.unroute('**/api/v1/conversations')
  }
})
