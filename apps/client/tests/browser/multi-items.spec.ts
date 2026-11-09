import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

async function configure(context: BrowserContext) {
  const session = await context.request.get('/api/v1/session')
  const csrf = (await session.json()).csrf_token
  const headers = { 'Content-Type': 'application/json', 'X-DSA-CSRF': csrf }
  const tested = await context.request.post('/api/v1/config/models/test', { headers, data: {
    name: 'Synthetic multi-item browser', provider: 'custom', base_url: 'https://models.example.com/v1',
    api_mode: 'chat_completions', model: 'synthetic-s2', api_key: 'synthetic-s2-only-multi-' + Date.now(),
    consent: true, test_text: 'Synthetic configuration only',
  } })
  expect(tested.ok()).toBeTruthy()
  const saved = await context.request.post('/api/v1/config/models/save', { headers, data: { validation_id: (await tested.json()).validation_id, make_active: true } })
  expect(saved.ok()).toBeTruthy()
  return { id: (await saved.json()).config.id as string, headers }
}
async function enable(page: Page) {
  await expect(page.locator('.continuous-toggle')).not.toHaveAttribute('disabled')
  await page.locator('.continuous-toggle').click()
  await expect(page.getByText('启用本次对话的连续 AI 理解', { exact: true })).toBeVisible()
  await expect(page.getByText(/你后续保存的每条消息将自动发送给/)).toContainText('synthetic-s2')
  await expect(page.getByText(/你后续保存的每条消息将自动发送给/)).toContainText('API费用')
  await page.locator('.taro-model__confirm').click()
  await expect(page.locator('.continuous-toggle')).toHaveText('关闭连续 AI 理解')
}
async function send(page: Page, text: string) {
  await page.getByText('AI 对话', { exact: true }).click()
  await page.locator('.composer textarea').fill(text)
  await page.locator('.submit-button').click()
  await expect(page.locator('.message-bubble .message-text').filter({ hasText: text }).first()).toBeVisible()
}

test('synthetic model real local API: explicit continuous consent, 20-item draft followup, whole-list confirmation and reload', async ({ page, context }) => {
  test.setTimeout(60000)
  const config = await configure(context)
  const created: string[] = []
  let modelCalls = 0
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) modelCalls++ })
  page.on('response', async response => {
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.status() === 201) created.push((await response.json()).id)
  })
  const initial = 'SYNTHETIC_LIST_20 ' + Array.from({ length: 20 }, (_, index) => '合成物品' + String(index + 1).padStart(2, '0')).join('、') + '，总预算5000 CNY'
  try {
    await page.goto('/')
    await expect(page.locator('.composer textarea')).toBeEnabled()
    await page.locator('.continuous-toggle').click()
    await page.locator('.taro-model__cancel').click()
    await expect(page.locator('.continuous-toggle')).toHaveText('启用连续 AI 理解')
    expect(modelCalls).toBe(0)
    await enable(page)
    expect(modelCalls).toBe(0)
    await send(page, initial)
    await page.getByText('方案工作区', { exact: true }).click()
    await page.locator('.requirement-details-toggle').click()
    await expect(page.locator('.shopping-item')).toHaveCount(20)
    await expect(page.locator('.assistant-message')).toHaveCount(1)
    await expect(page.locator('.version-status')).toContainText('AI草稿')
    const first = await (await context.request.get('/api/v1/conversations/' + created[0] + '/demand')).json()
    expect(first.confirmed_version).toBeNull()
    expect(first.current_version.data.items).toHaveLength(20)
    expect(first.current_version.data.items.every((item: { confirmed: boolean }) => !item.confirmed)).toBe(true)
    const itemOneId = first.current_version.data.items[0].item_id

    await send(page, 'SYNTHETIC_LIST_CHANGE 添加合成物品21，移除合成物品02，合成物品01每件预算300 CNY，总预算6000 CNY')
    await page.getByText('方案工作区', { exact: true }).click()
    if (!(await page.locator('#demand-budget input, input#demand-budget').isVisible())) await page.locator('.requirement-details-toggle').click()
    await expect(page.locator('.shopping-item')).toHaveCount(21)
    await expect(page.locator('.assistant-message')).toHaveCount(2)
    await expect(page.locator('.shopping-item.item-removed')).toContainText('合成物品02')
    await expect(page.locator('#demand-budget input, input#demand-budget')).toHaveValue('6000')
    const firstItem = page.locator('.shopping-item').filter({ hasText: '合成物品01' })
    await firstItem.locator('.item-expand').click()
    await expect(firstItem.locator('.item-budget input, input.item-budget')).toHaveValue('300')
    await expect(firstItem.locator('.budget-basis.selected')).toHaveText('每件上限')
    const draft = await (await context.request.get('/api/v1/conversations/' + created[0] + '/demand')).json()
    expect(draft.current_version.data.items[0].item_id).toBe(itemOneId)
    expect(draft.current_version.data.items.filter((item: { status: string }) => item.status === 'active')).toHaveLength(20)
    expect(draft.versions.find((value: { id: string }) => value.id === first.current_version.id).data.items).toHaveLength(20)
    expect(draft.confirmed_version).toBeNull()
    expect(modelCalls).toBe(2)
    await page.locator('.alternatives-choice').filter({ hasText: /^接受替代方案$/ }).click()
    await page.locator('.demand-reviewed').click()
    await page.locator('.demand-confirm').click()
    await expect(page.locator('.version-status')).toContainText('用户已确认')
    await expect(page.locator('.search-sources')).toBeVisible()
    const confirmed = await (await context.request.get('/api/v1/conversations/' + created[0] + '/demand')).json()
    expect(confirmed.confirmed_version.data.items).toHaveLength(21)
    expect(confirmed.confirmed_version.data.items[0].confirmed).toBe(true)
    await page.getByText('生成站外搜索入口', { exact: true }).click()
    await expect(page.locator('.search-plan-item')).toHaveCount(20)
    await expect(page.locator('.external-search-button')).toHaveCount(60)
    await page.evaluate(() => {
      const scope = window as typeof window & { openedSearchTargets: string[] }
      scope.openedSearchTargets = []
      window.open = ((url: string) => { scope.openedSearchTargets.push(url); return null }) as typeof window.open
    })
    const jd = page.locator('.search-plan-item').first().locator('.search-platform').filter({ hasText: '京东' }).locator('.external-search-button')
    await jd.click()
    await page.locator('.taro-model__cancel').click()
    expect(await page.evaluate(() => (window as typeof window & { openedSearchTargets: string[] }).openedSearchTargets)).toEqual([])
    await jd.click()
    await page.locator('.taro-model__confirm').click()
    expect(await page.evaluate(() => (window as typeof window & { openedSearchTargets: string[] }).openedSearchTargets)).toEqual([confirmed.confirmed_version.data.items[0] && 'https://search.jd.com/Search?keyword=' + encodeURIComponent('合成物品01 单价上限300 CNY')])
    await expect(page.locator('.search-sources .notice-box')).toContainText('复制链接')

    const searchInput = page.locator('.search-plan-item').first().locator('.search-query-input input, input.search-query-input')
    await searchInput.fill('')
    await expect(jd).toHaveAttribute('disabled', '')
    await searchInput.fill('合成关键词 & 预算300')
    await jd.click()
    await page.locator('.taro-model__confirm').click()
    expect(await page.evaluate(() => (window as typeof window & { openedSearchTargets: string[] }).openedSearchTargets)).toEqual([
      'https://search.jd.com/Search?keyword=' + encodeURIComponent('合成物品01 单价上限300 CNY'),
      'https://search.jd.com/Search?keyword=' + encodeURIComponent('合成关键词 & 预算300'),
    ])
    const unchanged = await (await context.request.get('/api/v1/conversations/' + created[0] + '/demand')).json()
    expect(unchanged.confirmed_version.id).toBe(confirmed.confirmed_version.id)
    await page.getByText('AI 对话', { exact: true }).click()
    await page.locator('.composer textarea').focus()
    await expect(page.locator('.composer textarea')).toBeFocused()
    await expect(page.locator('.composer textarea')).toBeInViewport()
    await page.screenshot({ path: test.info().outputPath('synthetic-list-composer.png') })
    expect(modelCalls).toBe(2)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)

    await page.reload()
    await expect(page.locator('.continuous-toggle')).toHaveText('启用连续 AI 理解')
    if (!(await page.locator('.sidebar').isVisible())) await page.locator('.history-toggle').click()
    await page.locator('.history-item').filter({ hasText: 'SYNTHETIC_LIST_20' }).click()
    await page.getByText('方案工作区', { exact: true }).click()
    if (!(await page.locator('#demand-budget input, input#demand-budget').isVisible())) await page.locator('.requirement-details-toggle').click()
    await expect(page.locator('.shopping-item')).toHaveCount(21)
    await expect(page.locator('.assistant-message')).toHaveCount(2)
    await expect(page.locator('.version-status')).toContainText('用户已确认')
    expect(modelCalls).toBe(2)
    if (!(await page.locator('.sidebar').isVisible())) await page.locator('.history-toggle').click()
    await page.locator('.new-chat').click()
    await expect(page.locator('.continuous-toggle')).toHaveText('启用连续 AI 理解')
    await send(page, 'Synthetic separate conversation remains local only')
    await expect(page.locator('.shopping-item')).toHaveCount(0)
    await expect(page.locator('.assistant-message')).toHaveCount(0)
    expect(modelCalls).toBe(2)
    expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0)
  } finally {
    for (const id of created) await context.request.delete('/api/v1/conversations/' + id, { headers: config.headers })
    await context.request.delete('/api/v1/config/models/' + config.id, { headers: config.headers })
  }
})

test('synthetic model and injected timeout: continuous calls never retry automatically and disabling restores local-only mode', async ({ page, context }) => {
  const config = await configure(context)
  const created: string[] = []
  let calls = 0
  page.on('response', async response => {
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.status() === 201) created.push((await response.json()).id)
  })
  await page.route('**/demand/collaborate', route => {
    calls++
    return route.fulfill({ status: 504, json: { error: { code: 'PROVIDER_TIMEOUT', message: 'Synthetic timeout' } } })
  })
  try {
    await page.goto('/')
    await expect(page.locator('.composer textarea')).toBeEnabled()
    await enable(page)
    await send(page, 'Synthetic failure must keep the original')
    await expect(page.locator('body')).toContainText('PROVIDER_TIMEOUT')
    await expect(page.locator('.message-bubble .message-text')).toHaveCount(1)
    expect(calls).toBe(1)
    await page.locator('.continuous-toggle').click()
    await expect(page.locator('.continuous-toggle')).toHaveText('启用连续 AI 理解')
    await send(page, 'Synthetic followup while disabled')
    await expect(page.locator('.message-bubble .message-text')).toHaveCount(2)
    expect(calls).toBe(1)
    await expect(page.locator('.assistant-message:not(.stream-preview)')).toHaveCount(0)
    await expect(page.locator('.stream-failed')).toContainText('PROVIDER_TIMEOUT')
    expect((await (await context.request.get('/api/v1/conversations/' + created[0] + '/demand')).json()).current_version).toBeNull()
  } finally {
    for (const id of created) await context.request.delete('/api/v1/conversations/' + id, { headers: config.headers })
    await context.request.delete('/api/v1/config/models/' + config.id, { headers: config.headers })
  }
})

test('continuous consent binds the send and its exact message; a later grant or another tab cannot auto-submit it', async ({ page, context }) => {
  test.setTimeout(60000)
  const config = await configure(context)
  const created: string[] = []
  let modelCalls = 0
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) modelCalls++ })
  page.on('response', async response => {
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.status() === 201) created.push((await response.json()).id)
  })
  let release: () => void = () => {}
  let committed: () => void = () => {}
  const gate = new Promise<void>(resolve => { release = resolve })
  const saved = new Promise<void>(resolve => { committed = resolve })
  try {
    await page.goto('/')
    await enable(page)
    await page.route('**/conversations/*/messages', async route => {
      const response = await route.fetch()
      committed()
      await gate
      await route.fulfill({ response })
    })
    await page.locator('.composer textarea').fill('Synthetic send under the first consent')
    await page.locator('.submit-button').click()
    await saved
    await page.locator('.continuous-toggle').click()
    await enable(page)
    release()
    await expect(page.locator('.message-bubble .message-text')).toHaveCount(1)
    await expect(page.getByText('生成回复', { exact: true })).not.toHaveAttribute('disabled', '')
    expect((await (await context.request.get('/api/v1/conversations/' + created[0] + '/demand')).json()).current_version).toBeNull()
    expect(modelCalls).toBe(0)
    await page.unroute('**/conversations/*/messages')
    await send(page, 'Synthetic new send under the second consent')
    await expect(page.locator('.assistant-message')).toHaveCount(1)
    expect(modelCalls).toBe(1)

    await page.route('**/conversations/*/messages', async route => {
      const response = await route.fetch()
      const extra = await context.request.post('/api/v1/conversations/' + created[0] + '/messages', {
        headers: config.headers, data: { content: 'Synthetic message saved independently in another tab', client_message_id: crypto.randomUUID() },
      })
      expect(extra.ok()).toBeTruthy()
      await route.fulfill({ response })
    })
    await send(page, 'Synthetic message before a concurrent local message')
    await expect(page.locator('.message-bubble .message-text')).toHaveCount(4)
    await expect(page.getByText('生成回复', { exact: true })).not.toHaveAttribute('disabled', '')
    expect(modelCalls).toBe(1)
    await expect(page.locator('.assistant-message')).toHaveCount(1)
  } finally {
    release()
    for (const id of created) await context.request.delete('/api/v1/conversations/' + id, { headers: config.headers })
    await context.request.delete('/api/v1/config/models/' + config.id, { headers: config.headers })
  }
})
