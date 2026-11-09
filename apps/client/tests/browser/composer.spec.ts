import { test, expect } from '@playwright/test'

test('real local send: typed text enables the button and click saves exactly once', async ({ page }) => {
  const ids: string[] = []
  page.on('response', async response => {
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.ok()) ids.push((await response.json()).id)
  })
  try {
    await page.goto('/')
    await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible()
    await expect(page.locator('.config-return-button')).toBeVisible()
    await page.locator('.config-return-button').click()
    const input = page.locator('.composer textarea')
    const button = page.locator('.submit-button')
    await expect(button).toHaveAttribute('disabled', '')
    const text = 'Synthetic per-key save ' + Date.now()
    await input.pressSequentially(text)
    await expect(button).not.toHaveAttribute('disabled')
    await expect.poll(() => button.evaluate(element => Boolean((element as HTMLElement & { disabled?: boolean }).disabled))).toBe(false)
    await expect(button).toHaveCSS('opacity', '1')
    await button.click()
    await expect(page.locator('.message-text')).toHaveText(text)
    await expect(input).toHaveValue('')
    await expect(button).toHaveAttribute('disabled', '')
    expect(ids).toHaveLength(1)
  } finally {
    const { csrf_token } = await (await page.request.get('/api/v1/session')).json()
    for (const id of ids) expect((await page.request.delete('/api/v1/conversations/' + id, { headers: { 'X-DSA-CSRF': csrf_token, 'Content-Type': 'application/json' } })).ok()).toBeTruthy()
  }
})

test('real local send: Chinese IME does not submit candidates; Enter saves and Shift+Enter keeps a newline', async ({ page, context }) => {
  const ids: string[] = []
  let modelCalls = 0
  page.on('request', request => { if (request.url().endsWith('/demand/collaborate')) modelCalls++ })
  page.on('response', async response => {
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.ok()) ids.push((await response.json()).id)
  })
  try {
    await page.goto('/')
    await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible()
    await expect(page.locator('.config-return-button')).toBeVisible()
    await page.locator('.config-return-button').click()
    const input = page.locator('.composer textarea')
    await input.focus()
    const cdp = await context.newCDPSession(page)
    const original = '中文输入法合成测试椅子'
    await cdp.send('Input.imeSetComposition', { text: original, selectionStart: original.length, selectionEnd: original.length })
    await input.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 229, isComposing: true, bubbles: true })
    expect(ids).toHaveLength(0)
    await cdp.send('Input.insertText', { text: original })
    await expect(page.locator('.submit-button')).not.toHaveAttribute('disabled')
    await input.press('Shift+Enter')
    await cdp.send('Input.insertText', { text: '补充合成条件' })
    await expect(input).toHaveValue(original + '\n补充合成条件')
    expect(ids).toHaveLength(0)
    await input.press('Enter')
    await expect(page.locator('.message-text')).toHaveText(original + '\n补充合成条件')
    await expect(input).toHaveValue('')
    expect(ids).toHaveLength(1)
    expect(modelCalls).toBe(0)
  } finally {
    const { csrf_token } = await (await page.request.get('/api/v1/session')).json()
    for (const id of ids) expect((await page.request.delete('/api/v1/conversations/' + id, { headers: { 'X-DSA-CSRF': csrf_token, 'Content-Type': 'application/json' } })).ok()).toBeTruthy()
  }
})
