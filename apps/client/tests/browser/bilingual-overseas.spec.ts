import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import type { ChatMessage } from '../../src/api'
import type { DemandView } from '../../src/demand'

// Isolated synthetic service only. The real desktop service and shopping sites are never used.
test.use({ baseURL: 'http://127.0.0.1:18005' })

async function setup(page: Page, context: BrowserContext) {
  const session = await context.request.get('/api/v1/session')
  const headers = { 'X-DSA-CSRF': (await session.json()).csrf_token, 'Content-Type': 'application/json' }
  const tested = await context.request.post('/api/v1/config/models/test', { headers, data: {
    name: 'Synthetic bilingual handoff only', provider: 'custom', base_url: 'https://models.example.com/v1',
    api_mode: 'chat_completions', model: 'synthetic-s2', api_key: 'synthetic-s2-only-bilingual-' + Date.now(),
    consent: true, test_text: 'Synthetic configuration only',
  } })
  expect(tested.ok()).toBeTruthy()
  const saved = await context.request.post('/api/v1/config/models/save', { headers, data: {
    validation_id: (await tested.json()).validation_id, make_active: true,
  } })
  expect(saved.ok()).toBeTruthy()
  const configId = (await saved.json()).config.id
  const ids: string[] = []
  page.on('response', async response => {
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.status() === 201) ids.push((await response.json()).id)
  })
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
  await page.locator('.continuous-toggle').click()
  await page.locator('.taro-model__confirm').click()
  return {
    view: async (): Promise<DemandView> => (await context.request.get('/api/v1/conversations/' + ids.at(-1) + '/demand')).json(),
    messages: async (): Promise<ChatMessage[]> => (await (await context.request.get('/api/v1/conversations/' + ids.at(-1))).json()).messages,
    cleanup: async () => {
      for (const id of ids) await context.request.delete('/api/v1/conversations/' + id, { headers })
      await context.request.delete('/api/v1/config/models/' + configId, { headers })
    },
  }
}

async function language(page: Page, target: '中文' | 'English') {
  await page.locator('.toolbar .language-switch').getByText(target, { exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('lang', target === 'English' ? 'en' : 'zh-CN')
}

async function chat(page: Page) { await page.locator('.page-tabs').getByText(/^(AI 对话|AI chat)$/).click() }
async function workspace(page: Page) { await page.locator('.page-tabs').getByText(/^(方案工作区|Plan workspace)$/).click() }

async function send(page: Page, text: string) {
  await chat(page)
  await page.locator('.composer textarea').fill(text)
  await page.locator('.submit-button').click()
  await expect(page.locator('.message-bubble .message-text').filter({ hasText: text }).first()).toBeVisible()
}

async function confirm(page: Page) {
  await workspace(page)
  if (!(await page.locator('.requirement-details').isVisible())) await page.locator('.requirement-details-toggle').click()
  await page.locator('.alternatives-choice').filter({ hasText: /^(接受替代方案|Accept alternatives)$/ }).click()
  await page.locator('.demand-reviewed').click()
  await page.locator('.demand-confirm').click()
  await expect(page.locator('.version-status')).toContainText(/用户已确认|Confirmed by you/)
}

test('synthetic language switching preserves editor, original words, confirmation and historical reference without model calls', async ({ page, context }) => {
  test.setTimeout(60000)
  const state = await setup(page, context)
  let modelCalls = 0
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) modelCalls++ })
  const original = 'SYNTHETIC_HOME 先给两个逐步改善居住舒适度的方向。'
  const editedGoal = '合成未保存目标 / synthetic unsaved goal'
  const feedback = 'Synthetic feedback 保留原话，不自动确认或翻译。'
  try {
    await send(page, original)
    await expect(page.locator('.assistant-reply')).toHaveCount(1)
    const firstReply = await page.locator('.assistant-reply').innerText()
    const first = await state.view()
    expect(first.confirmed_version).toBeNull()

    await workspace(page)
    await page.locator('.requirement-details-toggle').click()
    const goal = page.locator('#demand-goal textarea, textarea#demand-goal')
    await goal.fill(editedGoal)
    await language(page, 'English')
    await expect(goal).toHaveValue(editedGoal)
    await expect(page.locator('.editing-notice')).toContainText('unsaved')
    await expect(page.locator('.original-evidence .message-text')).toHaveText(original)
    await language(page, '中文')
    await expect(goal).toHaveValue(editedGoal)
    expect(await state.view()).toEqual(first)
    expect(modelCalls).toBe(1)

    await confirm(page)
    const confirmed = await state.view()
    expect(confirmed.confirmed_version!.data.desired_outcome).toBe(editedGoal)
    expect(confirmed.versions).toHaveLength(2)
    await chat(page)
    await page.locator('.continuous-toggle').click()
    await page.locator('.reference-reply').first().click()
    await page.locator('.composer textarea').fill(feedback)
    await expect(page.locator('.composer-reference')).toContainText('版本 1')

    let mutations = 0, configRequests = 0
    page.on('request', request => {
      if (request.method() !== 'GET' && new URL(request.url()).pathname.startsWith('/api/v1/conversations')) mutations++
      if (new URL(request.url()).pathname.startsWith('/api/v1/config/')) configRequests++
    })
    await language(page, 'English')
    await expect(page.locator('.composer textarea')).toHaveValue(feedback)
    await expect(page.locator('.composer-reference')).toContainText('1')
    await expect(page.locator('.assistant-reply')).toHaveText(firstReply)
    await workspace(page)
    await expect(page.locator('.version-status')).toContainText('Confirmed by you')
    await expect(goal).toHaveValue(editedGoal)
    await chat(page)
    await language(page, '中文')
    await expect(page.locator('.composer-reference')).toContainText('版本 1')
    await expect(page.locator('.composer textarea')).toHaveValue(feedback)
    expect(await state.view()).toEqual(confirmed)
    expect(mutations).toBe(0)
    expect(configRequests).toBe(0)
    expect(modelCalls).toBe(1)

    await language(page, 'English')
    await page.locator('.submit-button').click()
    await expect(page.locator('.message-reference')).toContainText('Referenced version 1')
    await expect(page.locator('.composer-reference')).toHaveCount(0)
    const messages = await state.messages()
    expect(messages.find(message => message.content === original)?.content).toBe(original)
    expect(messages.at(-1)?.content).toBe(feedback)
    expect(messages.at(-1)?.metadata?.reference_version?.id).toBe(first.current_version!.id)
    expect(modelCalls).toBe(1)

    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
    await expect(page).toHaveTitle('Demand Search App')
    await page.locator('.history-item').filter({ hasText: original }).click()
    await expect(page.locator('.message-reference')).toContainText('Referenced version 1')
    await expect(page.locator('.message-bubble .message-text').filter({ hasText: original }).first()).toHaveText(original)
    await expect(page.locator('.assistant-reply')).toHaveText(firstReply)
    expect(await state.view()).toEqual(confirmed)
    expect(modelCalls).toBe(1)
    await language(page, '中文')
    await expect(page.locator('.message-reference')).toContainText('引用版本 1')
  } finally { await state.cleanup() }
})

test('synthetic seven-platform handoffs preserve keywords and version, require confirmation and use fixed international URLs', async ({ page, context }) => {
  test.setTimeout(60000)
  const state = await setup(page, context)
  let modelCalls = 0
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) modelCalls++ })
  try {
    await send(page, 'SYNTHETIC_SEARCH 搜索办公椅，预算1500 CNY。')
    await expect(page.locator('.assistant-reply')).toHaveCount(1)
    await confirm(page)
    const confirmed = await state.view()
    await page.getByText('生成站外搜索入口', { exact: true }).click()
    await expect(page.locator('.search-plan-item')).toHaveCount(1)
    await expect(page.locator('.external-search-button')).toHaveCount(3)
    const query = 'desk lamp 台灯 & 预算300 CNY'
    const input = page.locator('.search-query-input input, input.search-query-input')
    await input.fill(query)
    await language(page, 'English')
    await expect(input).toHaveValue(query)
    await expect(page.locator('.market-option.selected')).toHaveText('China')
    await page.locator('.market-option').filter({ hasText: /^International$/ }).click()
    await expect(page.locator('.external-search-button')).toHaveCount(4)
    await expect(page.locator('.international-note')).toContainText('currency')
    await expect(page.locator('.search-platform .config-name')).toHaveText(['Amazon US', 'eBay US', 'Walmart US', 'Etsy'])
    await language(page, '中文')
    await expect(page.locator('.market-option.selected')).toHaveText('海外平台')
    await expect(input).toHaveValue(query)
    await language(page, 'English')
    await page.locator('.market-option').filter({ hasText: /^All platforms$/ }).click()
    await expect(page.locator('.external-search-button')).toHaveCount(7)

    await page.evaluate(() => {
      const scope = window as typeof window & { bilingualOpened: { url: string; target: string; features: string }[] }
      scope.bilingualOpened = []
      window.open = ((url: string, target: string, features: string) => {
        scope.bilingualOpened.push({ url, target, features })
        return null
      }) as typeof window.open
    })
    const readOpened = () => page.evaluate(() => (window as typeof window & { bilingualOpened: { url: string; target: string; features: string }[] }).bilingualOpened)
    const destinations: [string, string][] = [
      ['Taobao', 'https://s.taobao.com/search?q='],
      ['JD.com', 'https://search.jd.com/Search?keyword='],
      ['Pinduoduo', 'https://mobile.yangkeduo.com/search_result.html?search_key='],
      ['Amazon US', 'https://www.amazon.com/s?k='],
      ['eBay US', 'https://www.ebay.com/sch/i.html?_nkw='],
      ['Walmart US', 'https://www.walmart.com/search?q='],
      ['Etsy', 'https://www.etsy.com/search?q='],
    ]
    for (const [index, [name, prefix]] of destinations.entries()) {
      const button = page.locator('.search-platform').filter({ has: page.getByText(name, { exact: true }) }).locator('.external-search-button')
      await button.click()
      await expect(page.locator('.taro-modal__title')).toHaveText('Continue searching on platform')
      await expect(page.locator('.taro-modal__content')).toContainText(query)
      await expect(page.locator('.taro-modal__content')).toContainText(name)
      if (index === 0) {
        await page.locator('.taro-model__cancel').click()
        expect(await readOpened()).toEqual([])
        await button.click()
      }
      await page.locator('.taro-model__confirm').click()
      expect((await readOpened()).at(-1)).toEqual({ url: prefix + encodeURIComponent(query), target: '_blank', features: 'noopener,noreferrer' })
    }
    expect(await readOpened()).toHaveLength(7)
    await expect(input).toHaveValue(query)
    expect(await state.view()).toEqual(confirmed)
    expect(modelCalls).toBe(1)
    await expect(page.locator('.search-sources')).toContainText('No product or affiliate API is connected')
  } finally { await state.cleanup() }
})
