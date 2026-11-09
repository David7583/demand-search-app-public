import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

// New scenario calls use an independent synthetic service, preserving real rate limits.
test.use({ baseURL: 'http://127.0.0.1:18002' })

async function setup(page: Page, context: BrowserContext) {
  const session = await context.request.get('/api/v1/session')
  const headers = { 'X-DSA-CSRF': (await session.json()).csrf_token, 'Content-Type': 'application/json' }
  const validation = await context.request.post('/api/v1/config/models/test', { headers, data: {
    name: 'Synthetic collaboration only', provider: 'custom', base_url: 'https://models.example.com/v1',
    api_mode: 'chat_completions', model: 'synthetic-s2', api_key: 'synthetic-s2-only-collaboration-' + Date.now(),
    consent: true, test_text: 'Synthetic setup',
  } })
  expect(validation.ok()).toBeTruthy()
  const saved = await context.request.post('/api/v1/config/models/save', { headers, data: { validation_id: (await validation.json()).validation_id, make_active: true } })
  const configId = (await saved.json()).config.id
  const ids: string[] = []
  page.on('response', async response => {
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.status() === 201) ids.push((await response.json()).id)
  })
  await page.goto('/')
  await page.locator('.continuous-toggle').click()
  await page.locator('.taro-model__confirm').click()
  return {
    ids, headers,
    view: async () => (await context.request.get('/api/v1/conversations/' + ids.at(-1) + '/demand')).json(),
    cleanup: async () => {
      for (const id of ids) await context.request.delete('/api/v1/conversations/' + id, { headers })
      await context.request.delete('/api/v1/config/models/' + configId, { headers })
    },
  }
}
async function send(page: Page, text: string) {
  await page.getByText('AI 对话', { exact: true }).click()
  await page.locator('.composer textarea').fill(text)
  await page.locator('.submit-button').click()
  await expect(page.locator('.message-bubble').last()).toContainText(text)
}
async function workspace(page: Page) { await page.getByText('方案工作区', { exact: true }).click() }
async function details(page: Page) {
  if (!(await page.locator('.requirement-details').isVisible())) await page.locator('.requirement-details-toggle').click()
}
test('synthetic three-scenario contrast: explore, plan and execute switch within one task with useful first output', async ({ page, context }, testInfo) => {
  test.setTimeout(60000)
  const state = await setup(page, context)
  try {
    await send(page, 'SYNTHETIC_EXPLORE 我想买点东西改善生活，但没想清楚需要什么。')
    await expect(page.locator('.assistant-reply').last()).toContainText('两个方向')
    await workspace(page)
    await expect(page.locator('.solution-option')).toHaveCount(2)
    let view = await state.view()
    expect(view.current_version.data.collaboration.strategy).toBe('explore_first')
    expect(view.current_version.data.clarification_questions.length).toBeLessThanOrEqual(2)
    expect(view.confirmed_version).toBeNull()
    const firstId = view.current_version.id
    await send(page, 'SYNTHETIC_HOME SYNTHETIC_STREAM_SLOW 先帮我规划家装改善，不大拆，优先舒适。')
    await expect(page.locator('.stream-preview')).toBeVisible()
    expect((await state.view()).current_version.id).toBe(firstId)
    await expect(page.locator('.assistant-reply').last()).toContainText('初步方案')
    await workspace(page)
    await expect(page.locator('.solution-option')).toHaveCount(2)
    await expect(page.locator('.estimate')).toContainText('不是商家报价')
    view = await state.view()
    expect(view.current_version.data.collaboration.strategy).toBe('plan_first')
    expect(view.current_version.data.budget_ceiling).toBeNull()
    expect(view.versions).toHaveLength(2)
    expect(view.confirmed_version).toBeNull()
    await page.getByText('并排协作', { exact: true }).click()
    await expect(page.locator('.chat-page')).toBeVisible()
    await expect(page.locator('.solution-page')).toBeVisible()
    await page.getByText('折叠侧栏', { exact: true }).click()
    await expect(page.locator('.shell')).toHaveClass(/sidebar-collapsed/)
    await page.screenshot({ path: testInfo.outputPath('synthetic-collaboration-split.png') })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    await page.getByText('展开侧栏', { exact: true }).click()
    await workspace(page)
    await page.locator('.solution-scroll').evaluate(node => { node.scrollTop = 180 })
    const before = await page.locator('.solution-scroll').evaluate(node => node.scrollTop)
    expect(before).toBeGreaterThan(0)
    await page.getByText('AI 对话', { exact: true }).click()
    await workspace(page)
    expect(await page.locator('.solution-scroll').evaluate(node => node.scrollTop)).toBe(before)
    await send(page, 'SYNTHETIC_SEARCH 先搜索办公椅，预算1500 CNY，直接整理关键词。')
    await expect(page.locator('.assistant-reply').last()).toContainText('搜索入口')
    view = await state.view()
    expect(view.current_version.data.collaboration.strategy).toBe('execute_first')
    expect(view.current_version.data.clarification_questions).toEqual([])
    expect(view.versions).toHaveLength(3)
    expect(view.confirmed_version).toBeNull()
    expect(state.ids).toHaveLength(1)
    await workspace(page); await details(page)
    await page.getByText('接受替代方案', { exact: true }).click()
    await page.locator('.demand-reviewed').click()
    await page.locator('.demand-confirm').click()
    await expect(page.locator('.version-status')).toContainText('用户已确认')
    await page.getByText('生成站外搜索入口', { exact: true }).click()
    await expect(page.locator('.external-search-button')).toHaveCount(3)
    await expect(page.locator('.search-sources')).toContainText('搜索')
    expect((await state.view()).confirmed_version.data.solution_confirmed).toBe(false)
  } finally { await state.cleanup() }
})
test('synthetic workspace feedback keeps edits across pages and creates a new provisional plan without confirming estimates', async ({ page, context }) => {
  const state = await setup(page, context)
  try {
    await send(page, 'SYNTHETIC_HOME 希望先有一份家装改善方案。')
    await expect(page.locator('.assistant-reply')).toHaveCount(1)
    await workspace(page); await details(page)
    await page.locator('#demand-goal textarea, textarea#demand-goal').fill('SYNTHETIC_FEEDBACK 减少装饰，优先实用')
    await page.getByText('AI 对话', { exact: true }).click(); await workspace(page)
    await expect(page.locator('#demand-goal textarea, textarea#demand-goal')).toHaveValue('SYNTHETIC_FEEDBACK 减少装饰，优先实用')
    await page.getByText('作为修改意见带回对话', { exact: true }).click()
    await expect(page.locator('.composer textarea')).toHaveValue(/SYNTHETIC_FEEDBACK/)
    expect((await state.view()).versions).toHaveLength(1)
    await page.locator('.submit-button').click()
    await expect(page.locator('.assistant-reply')).toHaveCount(2)
    const view = await state.view()
    expect(view.versions).toHaveLength(2)
    expect(view.confirmed_version).toBeNull()
    expect(view.current_version.data.budget_ceiling).toBeNull()
    expect(view.current_version.data.solution_confirmed).toBe(false)
    await workspace(page)
    await page.locator('.choose-option').first().click()
    await details(page)
    await page.getByText('接受替代方案', { exact: true }).click()
    await page.locator('.solution-reviewed').click()
    await page.locator('.demand-reviewed').click()
    await page.locator('.demand-confirm').click()
    await expect(page.locator('.proposal-badge')).toContainText('已明确采纳')
    const confirmed = await state.view()
    expect(confirmed.confirmed_version.data.solution_confirmed).toBe(true)
    expect(confirmed.confirmed_version.data.budget_ceiling).toBeNull()
    expect(confirmed.confirmed_version.data.collaboration.assumptions.length).toBeGreaterThan(0)
  } finally { await state.cleanup() }
})
test('synthetic high-risk request asks necessary verification; broken stream preserves prior version without retry', async ({ page, context }) => {
  const state = await setup(page, context)
  try {
    await send(page, 'SYNTHETIC_RISK 我想拆承重墙扩大空间，能直接告诉我步骤吗？')
    await expect(page.locator('.assistant-reply')).toContainText('不能凭聊天判断')
    await workspace(page)
    await expect(page.locator('.verification-note')).toBeVisible()
    const before = await state.view()
    expect(before.current_version.data.collaboration.strategy).toBe('verify_first')
    let calls = 0
    page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) calls++ })
    await send(page, 'SYNTHETIC_STREAM_FAILURE 请继续讨论。')
    await expect(page.locator('.stream-failed')).toBeVisible()
    await expect(page.locator('.stream-failed')).toContainText('PROVIDER_STREAM_INTERRUPTED')
    expect(calls).toBe(1)
    const after = await state.view()
    expect(after.current_version.id).toBe(before.current_version.id)
    expect(after.confirmed_version).toEqual(before.confirmed_version)
    expect(after.versions).toHaveLength(1)
    await expect(page.locator('.composer textarea')).toBeEnabled()
    await workspace(page)
    await expect(page.locator('.version-status')).toContainText('版本 1')
  } finally { await state.cleanup() }
})

test('synthetic stream cancellation and task switch isolate temporary replies; invalid edits diagnose and explicit deletion resets the task', async ({ page, context }) => {
  test.setTimeout(60000)
  const state = await setup(page, context)
  const enable = async () => { await page.locator('.continuous-toggle').click(); await page.locator('.taro-model__confirm').click() }
  try {
    await send(page, 'SYNTHETIC_HOME SYNTHETIC_STREAM_SLOW 第一份合成方案，测试主动停止。')
    await expect(page.locator('.stream-preview')).toBeVisible()
    await page.locator('.stop-reply').click()
    await expect(page.locator('.stream-failed')).toContainText('STREAM_CANCELLED')
    await page.locator('.new-chat').click()
    await enable()
    await send(page, 'SYNTHETIC_HOME SYNTHETIC_STREAM_SLOW 第二份合成方案，测试流中切换任务。')
    await expect(page.locator('.stream-preview')).toBeVisible()
    await page.locator('.new-chat').click()
    await expect(page.locator('.stream-preview')).toHaveCount(0)
    await enable()
    await send(page, 'SYNTHETIC_SEARCH 办公椅1500 CNY，第三个独立任务。')
    await expect(page.locator('.assistant-reply')).toHaveCount(1)
    await expect(page.locator('.messages')).not.toContainText('第一份合成方案')
    await expect(page.locator('.messages')).not.toContainText('第二份合成方案')
    expect(state.ids).toHaveLength(3)
    for (const id of state.ids.slice(0, 2)) {
      const old = await (await context.request.get('/api/v1/conversations/' + id + '/demand')).json()
      expect(old.current_version).toBeNull()
      expect(old.confirmed_version).toBeNull()
    }
    await workspace(page); await details(page)
    await page.locator('.item-expand').first().click()
    await page.locator('.item-quantity input, input.item-quantity').fill('0')
    await page.getByText('作为修改意见带回对话', { exact: true }).click()
    await expect(page.locator('.demand-panel .error-box')).toContainText('请检查每项')
    await expect(page.locator('.item-quantity input, input.item-quantity')).toHaveValue('0')
    await expect(page.locator('.editing-notice')).toBeVisible()
    await page.locator('.task-bar').getByText('删除', { exact: true }).click()
    await page.locator('.taro-model__confirm').click()
    await expect(page.locator('.demand-panel')).toHaveCount(0)
    await expect(page.locator('.message-bubble')).toHaveCount(0)
    await expect(page.locator('.composer textarea')).toBeEnabled()
    expect((await context.request.get('/api/v1/conversations/' + state.ids.at(-1))).status()).toBe(404)
  } finally { await state.cleanup() }
})
