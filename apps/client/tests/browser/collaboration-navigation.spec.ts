import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

// Independent synthetic process: do not relax production provider rate limits.
test.use({ baseURL: 'http://127.0.0.1:18003' })

async function fixture(page: Page, context: BrowserContext, model = true) {
  const session = await context.request.get('/api/v1/session')
  const headers = { 'X-DSA-CSRF': (await session.json()).csrf_token, 'Content-Type': 'application/json' }
  const ids: string[] = []
  let configId: string | null = null
  if (model) {
    const validation = await context.request.post('/api/v1/config/models/test', { headers, data: {
      name: 'Synthetic UI recovery', provider: 'custom', base_url: 'https://models.example.com/v1',
      api_mode: 'chat_completions', model: 'synthetic-s2', api_key: 'synthetic-s2-only-ui-recovery-' + Date.now(),
      consent: true, test_text: 'Synthetic configuration only',
    } })
    expect(validation.ok()).toBeTruthy()
    const saved = await context.request.post('/api/v1/config/models/save', { headers, data: { validation_id: (await validation.json()).validation_id, make_active: true } })
    configId = (await saved.json()).config.id
  }
  page.on('response', async response => {
    if (response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/conversations' && response.status() === 201) ids.push((await response.json()).id)
  })
  return {
    create: async (title: string) => {
      const response = await context.request.post('/api/v1/conversations', { headers, data: { title } })
      const value = await response.json(); ids.push(value.id); return value.id
    },
    open: async () => {
      await page.goto('/')
      if (model) { await page.locator('.continuous-toggle').click(); await page.locator('.taro-model__confirm').click() }
      else await page.locator('.config-return-button').click()
    },
    cleanup: async () => {
      for (const id of ids) await context.request.delete('/api/v1/conversations/' + id, { headers })
      if (configId) await context.request.delete('/api/v1/config/models/' + configId, { headers })
    },
  }
}
async function send(page: Page, value: string) {
  await page.getByText('AI 对话', { exact: true }).click()
  await page.locator('.composer textarea').fill(value)
  await page.locator('.submit-button').click()
  await expect(page.locator('.message-bubble').last()).toContainText(value)
}

test('synthetic historical reply selects its own immutable version and refuses dirty or in-flight replacement', async ({ page, context }) => {
  const state = await fixture(page, context)
  try {
    await state.open()
    await send(page, 'SYNTHETIC_HOME 先讨论改善居住。')
    await expect(page.locator('.assistant-reply')).toHaveCount(1)
    await send(page, 'SYNTHETIC_FEEDBACK 优先实用，再给一份方案。')
    await expect(page.locator('.assistant-reply')).toHaveCount(2)
    await page.locator('.view-workspace').first().click()
    await expect(page.locator('.version-status')).toContainText('版本 1')
    await expect(page.locator('.version-status')).toContainText('历史只读')
    await expect(page.locator('.historical-context-note')).toContainText('当前方案')
    await page.getByText('回到当前版本', { exact: true }).click()
    await page.locator('.requirement-details-toggle').click()
    const goal = page.locator('#demand-goal textarea, textarea#demand-goal')
    await goal.fill('尚未保存，必须保留的修改')
    await page.getByText('AI 对话', { exact: true }).click()
    await page.locator('.view-workspace').first().click()
    await expect(page.locator('.version-status')).toContainText('版本 2')
    await expect(goal).toHaveValue('尚未保存，必须保留的修改')
    await expect(page.locator('.demand-panel .notice-box')).toContainText('当前编辑')
    await page.getByText('放弃未保存修改', { exact: true }).click()
    await send(page, 'SYNTHETIC_HOME SYNTHETIC_STREAM_SLOW 再讨论下一步。')
    await expect(page.locator('.stream-preview')).toBeVisible()
    await page.locator('.view-workspace').first().click()
    await expect(page.locator('.version-status')).toContainText('版本 2')
    await expect(page.locator('.demand-panel .notice-box')).toContainText('当前操作尚未完成')
    await expect(page.locator('.version-status')).toContainText('版本 3')
    await page.getByText('AI 对话', { exact: true }).click()
    await page.locator('.view-workspace').first().click()
    await expect(page.locator('.version-status')).toContainText('版本 1')
  } finally { await state.cleanup() }
})

test('synthetic unsent text survives cancelled new-task and history navigation without implicit save or AI calls', async ({ page, context }) => {
  const state = await fixture(page, context, false)
  const pageErrors: string[] = []
  page.on('pageerror', error => { pageErrors.push(error.message); console.log('SYNTHETIC_NAVIGATION_PAGEERROR', error.message) })
  try {
    await state.create('Synthetic task A')
    await state.create('Synthetic task B')
    await state.open()
    let messages = 0, modelCalls = 0
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/messages')) messages++
      if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) modelCalls++
    })
    const draft = '  Synthetic unsent text\n还没有发送，保留空格。  '
    await page.locator('.composer textarea').fill(draft)
    await page.locator('.new-chat').click()
    await expect(page.getByText('保留未发送文字？', { exact: true })).toBeVisible()
    await page.locator('.taro-model__cancel').click()
    await expect(page.locator('.composer textarea')).toHaveValue(draft)
    await page.locator('.history-item').filter({ hasText: 'Synthetic task A' }).click()
    await page.locator('.taro-model__cancel').click()
    await expect(page.locator('.composer textarea')).toHaveValue(draft)
    await expect(page.locator('.task-name')).toHaveText('新的需要')
    await page.locator('.history-item').filter({ hasText: 'Synthetic task A' }).click()
    await page.locator('.taro-model__confirm').click()
    await expect(page.locator('.task-name')).toHaveText('Synthetic task A')
    await expect(page.locator('.composer textarea')).toHaveValue('')
    await page.locator('.composer textarea').fill(draft)
    await page.locator('.history-item').filter({ hasText: 'Synthetic task B' }).click()
    await page.locator('.taro-model__cancel').click()
    await expect(page.locator('.task-name')).toHaveText('Synthetic task A')
    await expect(page.locator('.composer textarea')).toHaveValue(draft)
    await page.locator('.new-chat').click()
    await page.locator('.taro-model__confirm').click()
    await expect(page.locator('.task-name')).toHaveText('新的需要')
    await expect(page.locator('.composer textarea')).toHaveValue('')
    expect(messages).toBe(0)
    expect(modelCalls).toBe(0)
    expect(pageErrors).toEqual([])
  } finally { await state.cleanup() }
})

test('synthetic initial demand read failure is recoverable from chat without replaying the paid request', async ({ page, context }) => {
  const state = await fixture(page, context)
  try {
    await state.open()
    let denied = false, modelCalls = 0, reads = 0
    page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) modelCalls++ })
    await page.route('**/api/v1/conversations/*/demand', async route => {
      if (route.request().method() !== 'GET') return route.continue()
      reads++
      if (!denied) {
        denied = true
        return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'SYNTHETIC_READ_FAILURE', message: 'Synthetic demand read failed' } }) })
      }
      return route.continue()
    })
    await send(page, 'SYNTHETIC_HOME 原文保存后模拟方案读取失败。')
    await expect(page.locator('.demand-load-recovery')).toContainText('SYNTHETIC_READ_FAILURE')
    expect(await page.locator('.manual-reply').evaluate(node => node.hasAttribute('disabled'))).toBe(true)
    await page.locator('.manual-reply').click()
    await expect(page.locator('.taro-model__confirm')).not.toBeVisible()
    expect(modelCalls).toBe(0)
    await page.locator('.reload-demand').click()
    await expect(page.locator('.demand-load-recovery')).toHaveCount(0)
    await expect.poll(() => page.locator('.manual-reply').evaluate(node => node.hasAttribute('disabled'))).toBe(false)
    expect(reads).toBe(2)
    expect(modelCalls).toBe(0)
    await page.getByText('方案工作区', { exact: true }).click()
    await expect(page.locator('.demand-panel .notice-box')).toContainText('没有调用模型')
  } finally { await state.cleanup() }
})
