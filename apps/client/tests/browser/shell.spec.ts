import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

test('real local bootstrap: first-use wizard and memory-only secret input', async ({ page }, testInfo) => {
  const outbound: string[] = []
  const consoleMessages: string[] = []
  page.on('console', message => consoleMessages.push(message.text()))
  page.on('request', request => {
    if (request.method() === 'POST') outbound.push(request.url())
  })
  await page.goto('/')
  await expect(page.getByText('初始化与模型配置', { exact: true })).toBeVisible()
  const keyField = page.locator('input[type="password"]')
  await expect(keyField).toBeEnabled()
  const syntheticKey = 'synthetic-ui-only-' + 'x'.repeat(24)
  await keyField.fill(syntheticKey)
  await expect(page.locator('body')).not.toContainText(syntheticKey)
  await expect(page.getByText('测试连接并解析', { exact: true })).toHaveAttribute('disabled', '')
  await page.getByText('测试连接并解析', { exact: true }).click({ force: true })
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 })
  await page.getByText('返回主界面', { exact: true }).click()
  await page.getByText('设置', { exact: true }).click()
  await expect(page.locator('input[type="password"]')).toHaveValue('')
  expect(outbound).toEqual([])
  expect(consoleMessages.join('\n')).not.toContain(syntheticKey)
  await page.screenshot({ path: '../../.local/logs/s1-frontend-config-' + testInfo.project.name + '.png', fullPage: true, scale: 'css' })
})

test('real local history: save A and B, reload, resume A and export without a model', async ({ page }, testInfo) => {
  await page.goto('/')
  await page.getByText('返回主界面', { exact: true }).click()
  await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible()
  const openHistory = async () => {
    if (!(await page.locator('.sidebar').isVisible())) await page.locator('.history-toggle').click()
  }
  const newChat = async () => { await openHistory(); await page.locator('.new-chat').click() }
  const save = async (text: string) => {
    await page.locator('.composer textarea').fill(text)
    await page.getByText('发送 ↗', { exact: true }).click()
    await expect(page.locator('.message-text').filter({ hasText: text })).toBeVisible()
  }
  const id = Date.now().toString()
  const a = 'Synthetic A office chair ' + id
  const b = 'Synthetic B computer ' + id
  await newChat(); await save(a)
  await newChat(); await save(b)
  await expect(page.locator('.message-text')).not.toContainText(a)
  await page.reload()
  await page.getByText('返回主界面', { exact: true }).click()
  await openHistory()
  await page.locator('.history-item').filter({ hasText: a }).click()
  await expect(page.locator('.message-text')).toHaveText(a)
  const continuation = 'Synthetic A continuation'
  await save(continuation)
  await expect(page.locator('.message-text')).toHaveCount(2)
  await expect(page.getByText('生成回复', { exact: true })).toHaveAttribute('disabled', '')
  const downloadEvent = page.waitForEvent('download')
  await page.locator('.task-bar .compact-actions').getByText('导出', { exact: true }).click()
  const download = await downloadEvent
  const exportPath = testInfo.outputPath('synthetic-export.json')
  await download.saveAs(exportPath)
  const exported = await readFile(exportPath, 'utf8')
  expect(exported).toContain(a)
  expect(exported).not.toContain('"api_key"')
  expect(exported).not.toContain('"encrypted_secret"')
  await page.screenshot({ path: '../../.local/logs/s1-frontend-history-' + testInfo.project.name + '.png', fullPage: true, scale: 'css' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  const remove = async () => {
    await page.locator('.task-bar .compact-actions').getByText('删除', { exact: true }).click()
    await expect(page.getByText('删除本地会话', { exact: true })).toBeVisible()
    await page.locator('.taro-model__confirm').click()
    await expect(page.locator('.task-bar .compact-actions')).toHaveCount(0)
  }
  await remove()
  await openHistory()
  await page.locator('.history-item').filter({ hasText: b }).click()
  await remove()
})

test('mock_fixture only: model UI preserves old config on failure and returns to main after save and supports reopening switch delete', async ({ page }) => {
  let active = 'fixture-old'
  let configs = [{ id: 'fixture-old', name: 'fixture old config', provider: 'openai', base_url: 'https://api.openai.com/v1', api_mode: 'responses', model: 'fixture-old-model', key_mask: 'Windows protected fixture', verified_at: '2026-11-04T00:00:00Z', is_active: true }]
  let attempts = 0
  let releaseFirst: () => void = () => {}
  const firstResponse = new Promise<void>(resolve => { releaseFirst = resolve })
  await page.route('**/api/v1/config/models', route => route.fulfill({ json: { configs: configs.map(config => ({ ...config, is_active: config.id === active })), active_id: active } }))
  await page.route('**/api/v1/config/models/test', async route => {
    const payload = route.request().postDataJSON()
    expect(payload.consent).toBe(true)
    expect(payload.model).toBe('fixture-new-model')
    attempts++
    if (attempts === 1) { await firstResponse; return route.fulfill({ status: 401, json: { error: { code: 'MODEL_KEY_INVALID', message: '合成鉴权失败，旧配置保留' } } }) }
    return route.fulfill({ json: { validation_id: 'fixture-validation', expires_at: '2026-11-04T01:00:00Z', result: { requested_model: 'fixture-new-model', actual_model: 'fixture-actual-model', provider: 'openai', connection_status: 'verified', tested_at: '2026-11-04T00:00:00Z', parsed: { original_text: 'Synthetic fixture only', desired_outcome: 'Synthetic interpretation', user_confirmed: false } } } })
  })
  await page.route('**/api/v1/config/models/save', route => {
    expect(route.request().postDataJSON().validation_id).toBe('fixture-validation')
    active = 'fixture-new'
    configs.push({ ...configs[0], id: active, name: 'fixture new config', model: 'fixture-new-model' })
    return route.fulfill({ json: { config: configs[1], active_id: active } })
  })
  await page.route('**/api/v1/config/models/fixture-old/activate', route => { active = 'fixture-old'; return route.fulfill({ json: { active_id: active } }) })
  await page.route('**/api/v1/config/models/fixture-new', route => {
    expect(route.request().method()).toBe('DELETE')
    configs = configs.filter(config => config.id !== 'fixture-new')
    return route.fulfill({ json: { deleted: true, active_id: active } })
  })
  await page.goto('/')
  await expect(page.getByText('本地服务已连接', { exact: true })).toBeVisible()
  await page.getByText('设置', { exact: true }).click()
  await page.locator('#config-name input, input#config-name').fill('fixture new config')
  const synthetic = 'fixture-secret-' + 'z'.repeat(24)
  await page.locator('input[type=password]').fill(synthetic)
  await page.locator('#model-id input, input#model-id').fill('fixture-new-model')
  await page.locator('.consent-row').click()
  await page.getByText('测试连接并解析', { exact: true }).click()
  await expect(page.getByText('正在真实调用，请稍候…', { exact: true })).toHaveAttribute('disabled', '')
  await page.getByText('正在真实调用，请稍候…', { exact: true }).click({ force: true })
  expect(attempts).toBe(1)
  releaseFirst()
  await expect(page.getByText('合成鉴权失败，旧配置保留 [MODEL_KEY_INVALID]', { exact: true })).toBeVisible()
  await expect(page.getByText('fixture old config · 当前默认', { exact: true })).toBeVisible()
  await page.getByText('测试连接并解析', { exact: true }).click()
  await expect(page.getByText('实际模型：fixture-actual-model', { exact: true })).toBeVisible()
  await expect(page.locator('input[type=password]')).toHaveValue('')
  await expect(page.locator('body')).not.toContainText(synthetic)
  await page.getByText('保存并设为默认', { exact: true }).click()
  await expect(page.locator('.config-panel')).toHaveCount(0)
  await expect(page.getByText('模型配置已保存，可以开始记录需求。', { exact: true })).toBeVisible()
  await expect(page.locator('.composer textarea')).toBeEnabled()
  await page.locator('.composer textarea').fill('Synthetic setup completed; normal composer is available')
  await page.getByText('设置', { exact: true }).click()
  await expect(page.getByText('fixture new config · 当前默认', { exact: true })).toBeVisible()
  await page.locator('.saved-config').filter({ hasText: 'fixture new config' }).getByText('修改', { exact: true }).click()
  await expect(page.locator('#model-id input, input#model-id')).toHaveValue('fixture-new-model')
  await expect(page.locator('input[type=password]')).toHaveValue('')
  await page.locator('.config-panel').evaluate(element => { element.scrollTop = element.scrollHeight })
  await expect(page.getByText('返回主界面', { exact: true })).toBeInViewport()
  await page.getByText('返回主界面', { exact: true }).click()
  await expect(page.locator('.config-panel')).toHaveCount(0)
  await expect(page.locator('.composer textarea')).toHaveValue('Synthetic setup completed; normal composer is available')
  await page.getByText('设置', { exact: true }).click()
  await page.locator('.saved-config').filter({ hasText: 'fixture old config' }).getByText('切换', { exact: true }).click()
  await expect(page.getByText('fixture old config · 当前默认', { exact: true })).toBeVisible()
  await page.locator('.saved-config').filter({ hasText: 'fixture new config' }).getByText('删除', { exact: true }).click()
  await page.locator('.taro-model__confirm').click()
  await expect(page.locator('.saved-config').filter({ hasText: 'fixture new config' })).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0)
})
