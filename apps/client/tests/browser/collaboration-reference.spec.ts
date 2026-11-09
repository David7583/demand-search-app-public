import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import type { ChatMessage } from '../../src/api'
import type { DemandView } from '../../src/demand'

// Independent synthetic process; no real credentials, provider calls or private data.
test.use({ baseURL: 'http://127.0.0.1:18004' })
async function setup(page: Page, context: BrowserContext) {
  const session = await context.request.get('/api/v1/session')
  const headers = { 'X-DSA-CSRF': (await session.json()).csrf_token, 'Content-Type': 'application/json' }
  const validation = await context.request.post('/api/v1/config/models/test', { headers, data: {
    name: 'Synthetic version reference only', provider: 'custom', base_url: 'https://models.example.com/v1',
    api_mode: 'chat_completions', model: 'synthetic-s2', api_key: 'synthetic-s2-only-reference-' + Date.now(),
    consent: true, test_text: 'Synthetic configuration only',
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
  await expect(page.locator('.taro-modal__content')).toContainText('本条消息明确引用的同会话方案版本')
  await page.locator('.taro-model__confirm').click()
  return {
    ids,
    view: async (): Promise<DemandView> => (await context.request.get('/api/v1/conversations/' + ids.at(-1) + '/demand')).json(),
    messages: async (): Promise<ChatMessage[]> => (await (await context.request.get('/api/v1/conversations/' + ids.at(-1))).json()).messages,
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

test('synthetic saved historical reference survives reload and supplies the old plan while preserving current confirmation', async ({ page, context }) => {
  const state = await setup(page, context)
  try {
    await send(page, 'SYNTHETIC_HOME 最初的居住改善方案。')
    await expect(page.locator('.assistant-reply')).toHaveCount(1)
    const first = (await state.view()).current_version!
    await workspace(page)
    await page.locator('.requirement-details-toggle').click()
    await page.getByText('接受替代方案', { exact: true }).click()
    await page.locator('.demand-reviewed').click()
    await page.locator('.demand-confirm').click()
    await expect(page.locator('.version-status')).toContainText('用户已确认')
    const confirmation = (await state.view()).confirmed_version!
    await send(page, 'SYNTHETIC_SEARCH 先看办公椅的官方搜索入口。')
    await expect(page.locator('.assistant-reply')).toHaveCount(2)
    const before = await state.view()
    expect(before.current_version!.data.collaboration!.task_type).toBe('shopping')
    expect(before.current_version!.data.collaboration!.options).toEqual([])
    await page.locator('.continuous-toggle').click()
    await page.locator('.reference-reply').first().click()
    await expect(page.locator('.composer-reference')).toContainText('版本 1')
    let modelCalls = 0
    page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) modelCalls++ })
    await send(page, 'SYNTHETIC_REFERENCE 请具体沿用引用方案的内容讨论。')
    await expect(page.locator('.message-reference')).toContainText('引用版本 1')
    await expect(page.locator('.composer-reference')).toHaveCount(0)
    expect(modelCalls).toBe(0)
    const saved = (await state.messages()).at(-1)!
    expect(saved.metadata?.reference_version).toEqual({ id: first.id, number: first.number, status: first.status })
    await page.reload()
    await page.locator('.history-item').filter({ hasText: 'SYNTHETIC_HOME 最初的居住改善方案。' }).click()
    await expect(page.locator('.message-reference')).toContainText('引用版本 1')
    await expect(page.locator('.composer-reference')).toHaveCount(0)
    await expect.poll(() => page.locator('.manual-reply').evaluate(node => node.hasAttribute('disabled'))).toBe(false)
    await page.locator('.manual-reply').click()
    await expect(page.locator('.taro-modal__content')).toContainText('版本 1')
    await page.locator('.taro-model__confirm').click()
    await expect(page.locator('.assistant-reply')).toHaveCount(3)
    await expect(page.locator('.assistant-reply').last()).toContainText('已读取引用版本 1')
    await expect(page.locator('.assistant-reply').last()).toContainText(first.data.collaboration!.options[0].summary)
    expect(modelCalls).toBe(1)
    const after = await state.view()
    expect(after.current_version!.parent_version_id).toBe(before.current_version!.id)
    expect(after.current_version!.status).toBe('draft')
    expect(after.confirmed_version).toEqual(confirmation)
    expect(after.versions).toHaveLength(before.versions.length + 1)
  } finally { await state.cleanup() }
})

test('synthetic reference conflict and removal preserve text and unsent reference-only navigation remains explicit', async ({ page, context }) => {
  const state = await setup(page, context)
  try {
    await send(page, 'SYNTHETIC_HOME 第一份合成方案。')
    await expect(page.locator('.assistant-reply')).toHaveCount(1)
    await send(page, 'SYNTHETIC_FEEDBACK 再讨论更实用的方向。')
    await expect(page.locator('.assistant-reply')).toHaveCount(2)
    await page.locator('.continuous-toggle').click()
    let modelCalls = 0, messageCalls = 0
    page.on('request', request => {
      if (request.method() !== 'POST') return
      if (request.url().endsWith('/demand/collaborate')) modelCalls++
      if (request.url().endsWith('/messages')) messageCalls++
    })
    await page.locator('.reference-reply').first().click()
    const original = await page.locator('.composer textarea').inputValue()
    await page.locator('.reference-reply').last().click()
    await expect(page.locator('.chat-compose-area .error-box')).toContainText('请先移除该引用')
    await expect(page.locator('.composer-reference')).toContainText('版本 1')
    await expect(page.locator('.composer textarea')).toHaveValue(original)
    await page.locator('.remove-reference').click()
    await expect(page.locator('.composer-reference')).toHaveCount(0)
    await expect(page.locator('.composer textarea')).toHaveValue(original)
    await workspace(page)
    await page.getByText('讨论这个方向', { exact: true }).first().click()
    await expect(page.locator('.composer-reference')).toContainText('版本 2')
    await expect(page.locator('.composer textarea')).toHaveValue(new RegExp(original))
    await page.locator('.composer textarea').fill('')
    await page.locator('.new-chat').click()
    await expect(page.locator('.taro-modal__content')).toContainText('方案引用')
    await page.locator('.taro-model__cancel').click()
    await expect(page.locator('.composer-reference')).toContainText('版本 2')
    await page.locator('.new-chat').click()
    await page.locator('.taro-model__confirm').click()
    await expect(page.locator('.task-name')).toHaveText('新的需要')
    await expect(page.locator('.composer-reference')).toHaveCount(0)
    expect(modelCalls).toBe(0)
    expect(messageCalls).toBe(0)
  } finally { await state.cleanup() }
})

test('synthetic committed reference retries the identical message ID and version after a lost followup read', async ({ page, context }) => {
  const state = await setup(page, context)
  try {
    await send(page, 'SYNTHETIC_HOME 用于测试引用保存重试的方案。')
    await expect(page.locator('.assistant-reply')).toHaveCount(1)
    const reference = (await state.view()).current_version!
    await page.locator('.continuous-toggle').click()
    await workspace(page)
    await page.getByText('把反馈带回对话', { exact: true }).click()
    await expect(page.locator('.composer-reference')).toContainText('版本 1')
    let failRead = false, failedOnce = false, modelCalls = 0
    const sent: { content: string; client_message_id: string; reference_version_id: string }[] = []
    page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/demand/collaborate')) modelCalls++ })
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
    const text = 'Synthetic reference already saved despite missing read'
    await page.locator('.composer textarea').fill(text)
    await page.locator('.submit-button').click()
    await expect(page.locator('.chat-compose-area .error-box')).toContainText('NETWORK_ERROR')
    await expect(page.locator('.composer textarea')).toHaveValue(text)
    await expect(page.locator('.composer-reference')).toContainText('版本 1')
    await page.locator('.submit-button').click()
    await expect(page.locator('.message-reference')).toContainText('引用版本 1')
    await expect(page.locator('.composer-reference')).toHaveCount(0)
    expect(sent).toHaveLength(2)
    expect(sent[0]).toEqual(sent[1])
    expect(sent[0].reference_version_id).toBe(reference.id)
    const matching = (await state.messages()).filter(message => message.content === text)
    expect(matching).toHaveLength(1)
    expect(matching[0].metadata?.reference_version?.id).toBe(reference.id)
    expect(modelCalls).toBe(0)
  } finally { await state.cleanup() }
})
