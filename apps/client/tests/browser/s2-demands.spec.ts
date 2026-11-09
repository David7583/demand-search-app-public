import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

test('synthetic provider with real HTTP DPAPI: immutable demand versions, history isolation and private NCP export', async ({ page }, testInfo) => {
  test.setTimeout(60000)
  const session = await page.request.get('/api/v1/session')
  const csrf = (await session.json()).csrf_token as string
  const headers = { 'X-DSA-CSRF': csrf, 'Content-Type': 'application/json' }
  const tested = await page.request.post('/api/v1/config/models/test', { headers, data: {
    name: 'Synthetic S2 browser configuration', provider: 'custom', base_url: 'https://models.example.com/v1',
    api_mode: 'chat_completions', model: 'synthetic-s2', api_key: 'synthetic-s2-only-browser-' + Date.now(),
    consent: true, test_text: 'Synthetic configuration test only',
  } })
  expect(tested.ok(), await tested.text()).toBeTruthy()
  const saved = await page.request.post('/api/v1/config/models/save', { headers, data: { validation_id: (await tested.json()).validation_id, make_active: true } })
  expect(saved.ok()).toBeTruthy()
  const configId = (await saved.json()).config.id as string
  const created: string[] = []
  try {
    await page.goto('/')
    await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible()
    await expect(page.locator('.config-panel')).toHaveCount(0)
    const saveMessage = async (text: string) => {
      await page.getByText('AI 对话', { exact: true }).click()
      await page.locator('.composer textarea').fill(text)
      await page.getByText('发送 ↗', { exact: true }).click()
      await expect(page.locator('.message-text').filter({ hasText: text }).first()).toBeVisible()
    }
    const parse = async () => {
      await page.getByText('生成回复', { exact: true }).click()
      await expect(page.getByText('发送有限上下文给 AI', { exact: true })).toBeVisible()
      await page.locator('.taro-model__confirm').click()
      await page.getByText('方案工作区', { exact: true }).click()
      await expect(page.locator('.version-status')).toContainText('AI草稿')
      if (!(await page.locator('#demand-budget input, input#demand-budget').isVisible())) await page.locator('.requirement-details-toggle').click()
    }
    const confirm = async () => {
      await page.locator('.alternatives-choice').filter({ hasText: /^接受替代方案$/ }).click()
      await page.locator('.demand-reviewed').click()
      await expect(page.locator('.demand-confirm')).not.toHaveAttribute('disabled', '')
      const response = page.waitForResponse(item => item.url().endsWith('/demand/confirm'))
      await page.getByText('确认并保存新版本', { exact: true }).click()
      const confirmation = await response
      expect(await confirmation.json()).not.toHaveProperty('error')
      await expect(page.locator('.version-status')).toContainText('用户已确认')
    }
    const original = '预算1500元，想要适合久坐的办公椅。'
    await saveMessage(original)
    const conversations = await (await page.request.get('/api/v1/conversations')).json()
    const a = conversations.conversations.find((item: { title: string }) => item.title === original)
    created.push(a.id)
    await parse()
    await expect(page.locator('#demand-budget input, input#demand-budget')).toHaveValue('1500')
    await expect(page.locator('.demand-confirm')).toHaveAttribute('disabled', '')
    await confirm()
    await expect(page.locator('.version-status')).toContainText('版本 2')

    // Manual editing makes a new confirmed version; original text is immutable.
    await page.locator('#demand-budget input, input#demand-budget').fill('3000')
    await page.locator('.demand-reviewed').click()
    await page.getByText('确认并保存新版本', { exact: true }).click()
    await expect(page.locator('.version-status')).toContainText('版本 3')
    await expect(page.locator('.original-evidence')).toContainText(original)
    await page.locator('.version-item').filter({ hasText: '版本 2 · 已确认' }).click()
    await expect(page.locator('.version-status')).toContainText('历史只读')
    await expect(page.locator('#demand-budget input, input#demand-budget')).toHaveValue('1500')
    await expect(page.locator('#demand-budget input, input#demand-budget')).toBeDisabled()
    await page.locator('.version-status').scrollIntoViewIfNeeded()
    await page.screenshot({ path: '../../.local/logs/s2-demands-history-' + testInfo.project.name + '.png', scale: 'css' })
    await page.locator('#demand-budget input, input#demand-budget').scrollIntoViewIfNeeded()
    await page.screenshot({ path: '../../.local/logs/s2-demands-history-budget-' + testInfo.project.name + '.png', scale: 'css' })
    await page.getByText('回到当前版本', { exact: true }).click()
    await expect(page.locator('#demand-budget input, input#demand-budget')).toHaveValue('3000')

    const continuation = '预算3000元，保留适合久坐要求。'
    await saveMessage(continuation)
    await parse()
    await expect(page.locator('#demand-budget input, input#demand-budget')).toHaveValue('3000')
    await confirm()
    await expect(page.locator('.version-status')).toContainText('版本 5')
    const versions = await (await page.request.get('/api/v1/conversations/' + a.id + '/demand')).json()
    expect(versions.versions).toHaveLength(5)
    expect(versions.versions.find((version: { number: number }) => version.number === 2).data.budget_ceiling.amount).toBe(1500)
    expect(versions.current_version.original_text).toBe(continuation)

    const openHistory = async () => { if (!(await page.locator('.sidebar').isVisible())) await page.locator('.history-toggle').click() }
    await openHistory()
    await page.locator('.new-chat').click()
    const bText = 'Synthetic independent conversation B ' + Date.now()
    await saveMessage(bText)
    const bList = await (await page.request.get('/api/v1/conversations')).json()
    created.push(bList.conversations.find((item: { title: string }) => bText.startsWith(item.title)).id)
    await expect(page.locator('.version-status')).toHaveCount(0)
    await expect(page.locator('#demand-goal')).toHaveCount(0)
    await page.reload()
    await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible()
    await openHistory()
    await page.locator('.history-item').filter({ hasText: original }).click()
    await page.getByText('方案工作区', { exact: true }).click()
    await expect(page.locator('.version-status')).toContainText('版本 5')
    if (!(await page.locator('#demand-budget input, input#demand-budget').isVisible())) await page.locator('.requirement-details-toggle').click()
    await expect(page.locator('.messages')).not.toContainText(bText)
    await expect(page.locator('#demand-budget input, input#demand-budget')).toHaveValue('3000')

    await page.getByText('导出本地 NCP 消息', { exact: true }).click()
    await expect(page.getByText('导出私人需求', { exact: true })).toBeVisible()
    const downloadEvent = page.waitForEvent('download')
    await page.locator('.taro-model__confirm').click()
    const download = await downloadEvent
    const exportPath = testInfo.outputPath('synthetic-ncp-export.json')
    await download.saveAs(exportPath)
    const exported = JSON.parse(await readFile(exportPath, 'utf8'))
    expect(exported.protocol).toBe('ODIP/0.1.3-exp.1')
    expect(exported.sharing_scope).toBe('private')
    expect(exported.network_transmitted).toBe(false)
    expect(exported.packets.map((packet: { message_type: string }) => packet.message_type)).toEqual(['intent.publish', 'intent.update', 'intent.update'])
    expect(JSON.stringify(exported)).not.toContain('synthetic-s2-only-')
    await page.locator('#demand-budget input, input#demand-budget').scrollIntoViewIfNeeded()
    await page.screenshot({ path: '../../.local/logs/s2-demands-' + testInfo.project.name + '.png', scale: 'css' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)

    await page.getByText('撤回本地需求', { exact: true }).click()
    await expect(page.getByText('撤回本地需求', { exact: true }).last()).toBeVisible()
    await page.locator('.taro-model__confirm').click()
    await expect(page.getByText('本需求已撤回，不能继续修改。历史仍保留。', { exact: true })).toBeVisible()
    await page.getByText('AI 对话', { exact: true }).click()
    await expect(page.getByText('生成回复', { exact: true })).toHaveAttribute('disabled', '')
    const withdrawn = await (await page.request.get('/api/v1/conversations/' + a.id + '/demand')).json()
    expect(withdrawn.demand.status).toBe('withdrawn')
    expect(withdrawn.versions).toHaveLength(5)
  } finally {
    for (const id of created) await page.request.delete('/api/v1/conversations/' + id, { headers })
    await page.request.delete('/api/v1/config/models/' + configId, { headers })
  }
})
