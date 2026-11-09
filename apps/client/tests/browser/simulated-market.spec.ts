import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { DemandView } from '../../src/demand'
import type { SimulatedMatches } from '../../src/components/SimulatedMarket'

test('isolated simulated catalog and saved multi-item matches preserve versions and reject late responses', async ({ page, context }) => {
  test.setTimeout(90000)
  let conversationId = '', configId = ''
  const session = await context.request.get('/api/v1/session')
  const headers = { 'X-DSA-CSRF': (await session.json()).csrf_token, 'Content-Type': 'application/json' }
  let modelCalls = 0
  page.on('request', request => { if (/\/demand\/(parse|collaborate)$/.test(request.url())) modelCalls++ })
  try {
    await page.goto('/')
    await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible()
    await page.getByText('返回主界面', { exact: true }).click()
    await page.locator('.market-nav').click()
    await expect(page.locator('.market-count')).toHaveText('500 家虚构商家 · 1500 项模拟商品与服务')
    await expect(page.locator('.market-catalog > .market-offering')).toHaveCount(12)
    await expect(page.locator('.market-disclaimer')).toContainText('无需模型 Key')
    await page.screenshot({ path: '../../.local/logs/simulated-market/market.png' })
    const firstPage = await page.locator('.market-catalog .config-name').first().innerText()
    await page.locator('.market-next').click()
    await expect(page.locator('.market-catalog .config-name').first()).not.toHaveText(firstPage)
    const search = async (term: string) => {
      await page.locator('.market-query input, input.market-query').fill(term)
      const response = page.waitForResponse(value => value.request().method() === 'GET' && new URL(value.url()).pathname === '/api/v1/simulated-market' && new URL(value.url()).searchParams.get('query') === term)
      await page.locator('.market-search-button').click()
      expect((await response).ok()).toBeTruthy()
      await expect(page.locator('.market-search-button')).not.toHaveAttribute('disabled')
    }
    await search('办公椅')
    await expect(page.locator('.market-catalog')).toContainText('办公椅')
    await page.locator('.market-merchant-button').first().click()
    await page.locator('.market-merchant .market-json-toggle').click()
    await expect(page.locator('.market-merchant .market-json-content')).toContainText('ODIP/0.1.3-exp.1')
    await expect(page.locator('.market-merchant .market-json-content')).toContainText('synthetic')
    await page.locator('.market-close-merchant').click()
    await search('保洁')
    await expect(page.locator('.market-catalog > .market-offering').first()).toBeVisible()
    await expect(page.locator('.market-catalog')).toContainText('保洁')
    await page.locator('.toolbar .language-switch').getByText('English', { exact: true }).click()
    await expect(page.locator('.market-query input, input.market-query')).toHaveValue('保洁')
    await expect(page.locator('.market-disclaimer')).toContainText('fictional')
    await page.screenshot({ path: '../../.local/logs/simulated-market/catalog-en.png' })
    await page.locator('.toolbar .language-switch').getByText('中文', { exact: true }).click()

    // Seed a confirmed multi-item demand using only the existing synthetic model fixture.
    const tested = await context.request.post('/api/v1/config/models/test', { headers, data: {
      name: 'Synthetic market only', provider: 'custom', base_url: 'https://models.example.com/v1', api_mode: 'chat_completions',
      model: 'synthetic-s2', api_key: 'synthetic-s2-only-market-' + Date.now(), consent: true, test_text: 'Synthetic setup only',
    } })
    expect(tested.ok()).toBeTruthy()
    const saved = await context.request.post('/api/v1/config/models/save', { headers, data: { validation_id: (await tested.json()).validation_id, make_active: true } })
    expect(saved.ok()).toBeTruthy(); configId = (await saved.json()).config.id
    const conversation = await context.request.post('/api/v1/conversations', { headers, data: { title: 'Synthetic simulated market only' } })
    expect(conversation.ok()).toBeTruthy(); conversationId = (await conversation.json()).id
    const base = '/api/v1/conversations/' + conversationId + '/demand'
    const message = await context.request.post('/api/v1/conversations/' + conversationId + '/messages', { headers, data: { content: 'SYNTHETIC_LIST_20 合成多项清单，仅用于模拟市场浏览器验证。', client_message_id: randomUUID() } })
    expect(message.ok()).toBeTruthy()
    const parsed = await context.request.post(base + '/parse', { headers, data: { message_id: (await message.json()).message.id, expected_version_id: null, config_id: configId, consent: true, request_id: randomUUID() } })
    expect(parsed.ok()).toBeTruthy()
    const draft = (await parsed.json() as DemandView).current_version!
    const confirmedResponse = await context.request.post(base + '/confirm', { headers, data: {
      request_id: randomUUID(), version_id: draft.id, confirm: true, continue_current_intent: false,
      edits: { desired_outcome: '合成办公椅与台灯清单', required: [], preferred: [], unknown: ['实际配送条件待核实'], budget_ceiling: { amount: 3000, currency: 'CNY' }, readiness: 'need', alternatives_acceptable: true,
        items: draft.data.items!.map((item, index) => ({ item_id: item.item_id, name: index === 0 ? '办公椅' : index === 1 ? '台灯' : item.name, quantity: 1, unit: '件', required: [], preferred: [], unknown: ['尺寸待核实'], budget_ceiling: index < 2 ? { amount: index === 0 ? 1500 : 300, currency: 'CNY' } : null, budget_basis: 'unit', status: index < 2 ? 'active' : 'removed' })),
      },
    } })
    expect(confirmedResponse.ok()).toBeTruthy()
    const confirmed = await (await context.request.get(base)).json() as DemandView
    await page.reload()
    await page.locator('.history-item').filter({ hasText: 'Synthetic simulated market only' }).click()
    await page.locator('.page-tabs').getByText('方案工作区', { exact: true }).click()
    await expect(page.locator('.version-status')).toContainText('用户已确认')
    const responsePromise = page.waitForResponse(value => value.url().endsWith('/demand/simulated-market'))
    await page.locator('.market-match-button').click()
    const response = await responsePromise
    expect(response.request().postDataJSON()).toEqual({ version_id: confirmed.current_version!.id })
    const matches = await response.json() as SimulatedMatches
    expect(matches.version_id).toBe(confirmed.current_version!.id)
    expect(matches.network_searched).toBe(false)
    expect(matches.items).toHaveLength(2)
    for (const item of matches.items) {
      expect(item.matches.length).toBeGreaterThan(0)
      expect(item.matches.length).toBeLessThanOrEqual(3)
      expect(JSON.stringify(item.matches[0].proposal)).toContain(matches.intent_id)
      expect(JSON.stringify(item.matches[0].proposal)).toContain(item.matches[0].offering.id)
    }
    await expect(page.locator('.market-match-item')).toHaveCount(2)
    const firstCandidate = page.locator('.market-candidate').first()
    await expect(firstCandidate).toContainText('尺寸待核实')
    await firstCandidate.locator('.market-json-toggle').click()
    await expect(firstCandidate.locator('.market-json-content')).toContainText(matches.intent_id)
    await page.locator('.demand-market-matches').scrollIntoViewIfNeeded()
    await page.screenshot({ path: '../../.local/logs/simulated-market/matches-zh.png' })
    await firstCandidate.locator('.market-discuss').click()
    await expect(page.locator('.composer textarea')).toHaveValue(/讨论模拟候选/)
    await expect(page.locator('.composer-reference')).toContainText('版本 2')
    expect(modelCalls).toBe(0)
    expect(await (await context.request.get(base)).json()).toEqual(confirmed)
    await page.locator('.page-tabs').getByText('方案工作区', { exact: true }).click()
    await page.locator('.requirement-details-toggle').click()
    await page.locator('#demand-goal textarea, textarea#demand-goal').fill('尚未保存的目标')
    await expect(page.locator('.demand-market-matches .editing-notice')).toContainText('仍使用已保存版本')
    const dirtyResponse = page.waitForResponse(value => value.url().endsWith('/demand/simulated-market'))
    await page.locator('.market-match-button').click()
    expect((await dirtyResponse).request().postDataJSON()).toEqual({ version_id: confirmed.current_version!.id })
    await expect(page.locator('.market-match-item')).toHaveCount(2)
    await page.getByText('放弃未保存修改', { exact: true }).click()

    // A response arriving after switching to a draft cannot repopulate the old panel.
    let release!: () => void, fetched!: () => void
    const gate = new Promise<void>(resolve => { release = resolve })
    const requestFetched = new Promise<void>(resolve => { fetched = resolve })
    await page.route('**/demand/simulated-market', async route => { const value = await route.fetch(); fetched(); await gate; await route.fulfill({ response: value }) })
    await page.locator('.market-match-button').click()
    await requestFetched
    await page.locator('.version-item').filter({ hasText: '版本 1 · 草稿' }).click()
    await expect(page.locator('.demand-market-matches')).toHaveCount(0)
    const lateResponse = page.waitForResponse(value => value.url().endsWith('/demand/simulated-market'))
    release(); await lateResponse
    await page.unroute('**/demand/simulated-market')
    await page.locator('.version-item').filter({ hasText: '版本 2 · 已确认' }).click()
    await expect(page.locator('.market-match-item')).toHaveCount(0)
    expect(await (await context.request.get(base)).json()).toEqual(confirmed)
    expect(modelCalls).toBe(0)
  } finally {
    if (conversationId) await context.request.delete('/api/v1/conversations/' + conversationId, { headers })
    if (configId) await context.request.delete('/api/v1/config/models/' + configId, { headers })
  }
})
