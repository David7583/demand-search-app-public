import { expect, test } from '@playwright/test'

for (const existing of [false, true]) {
  test('real local message commit followed by read failure retries once without duplicates; existing=' + existing, async ({ page, context }) => {
    const ids: string[] = []
    page.on('response', async response => {
      if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.status() === 201) ids.push((await response.json()).id)
    })
    try {
      await page.goto('/')
      await expect(page.locator('.config-return-button')).toBeVisible()
      await page.locator('.config-return-button').click()
      if (existing) {
        await page.locator('.composer textarea').fill('Synthetic seed before lost response')
        await page.locator('.submit-button').click()
        await expect(page.locator('.message-text')).toHaveCount(1)
      }
      let failRead = false
      let failedOnce = false
      const sent: { content: string; client_message_id: string }[] = []
      await page.route('**/conversations/*/messages', async route => {
        if (route.request().method() !== 'POST') return route.continue()
        sent.push(route.request().postDataJSON())
        const response = await route.fetch()
        if (!failedOnce) failRead = true
        await route.fulfill({ response })
      })
      await page.route('**/conversations/*', route => {
        if (route.request().method() === 'GET' && /\/conversations\/[0-9a-f-]+$/.test(new URL(route.request().url()).pathname) && failRead) {
          failRead = false; failedOnce = true
          return route.abort('failed')
        }
        return route.fallback()
      })
      const text = 'Synthetic committed message with lost followup read'
      await page.locator('.composer textarea').fill(text)
      await page.locator('.submit-button').click()
      await expect(page.locator('.error-box')).toContainText('NETWORK_ERROR')
      await expect(page.locator('.composer textarea')).toHaveValue(text)
      await page.locator('.submit-button').click()
      await expect(page.locator('.message-text')).toHaveCount(existing ? 2 : 1)
      await expect(page.locator('.message-text').last()).toHaveText(text)
      expect(ids).toHaveLength(1)
      expect(sent).toHaveLength(2)
      expect(sent[0]).toEqual(sent[1])
      const detail = await (await context.request.get('/api/v1/conversations/' + ids[0])).json()
      expect(detail.messages.filter((message: { content: string }) => message.content === text)).toHaveLength(1)
    } finally {
      const { csrf_token } = await (await context.request.get('/api/v1/session')).json()
      for (const id of ids) expect((await context.request.delete('/api/v1/conversations/' + id, { headers: { 'X-DSA-CSRF': csrf_token, 'Content-Type': 'application/json' } })).ok()).toBeTruthy()
    }
  })
}
