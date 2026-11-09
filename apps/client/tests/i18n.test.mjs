import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import { normalizeLocale, translate, translateNotice, localeStorageKey } from '../src/i18n-core.ts'
import { english } from '../src/translations.ts'

test('locale defaults safely and preserves arbitrary content outside the interface catalog', () => {
  for (const value of [null, undefined, '', 'fr', '__proto__', {}, 'zh-CN']) assert.equal(normalizeLocale(value), 'zh-CN')
  assert.equal(normalizeLocale('en'), 'en')
  assert.equal(localeStorageKey, 'demand-search.interface-language')
  assert.equal(translate('AI 对话', 'en'), 'AI chat')
  assert.equal(translate('AI 对话', 'zh-CN'), 'AI 对话')
  for (const text of ['我的椅子 CNY 1500', 'A user original', 'ODIP/0.1.3-exp.1', '__proto__', 'constructor']) assert.equal(translate(text, 'en'), text)
  assert.equal(translateNotice('操作未完成，请重试。 [NETWORK_ERROR]', 'en'), 'Operation did not complete. Please try again. [NETWORK_ERROR]')
  assert.match(translateNotice('服务商拒绝测试 [PROVIDER_AUTH_FAILED]', 'en'), /rejected authentication.*\[PROVIDER_AUTH_FAILED\]/)
  assert.match(translateNotice('未知服务异常 [UNLISTED_ERROR]', 'en'), /diagnostic code.*\[UNLISTED_ERROR\]/)
  assert.equal(translateNotice('version 12', 'zh-CN'), '版本 12')
})

test('every literal interface translation call has a nonempty English entry', () => {
  const files = ['pages/chat/index.tsx', 'components/ModelSettings.tsx', 'components/DemandPanel.tsx', 'components/ShoppingListEditor.tsx', 'components/SolutionWorkspace.tsx', 'components/SearchSources.tsx', 'components/SimulatedMarket.tsx', 'i18n.tsx']
  let checked = 0
  for (const file of files) {
    const source = ts.createSourceFile(file, fs.readFileSync(new URL('../src/' + file, import.meta.url), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    function visit(node) {
      if (ts.isCallExpression(node) && node.expression.getText(source) === 't' && node.arguments[0] && ts.isStringLiteral(node.arguments[0])) {
        const key = node.arguments[0].text
        assert.ok(typeof english[key] === 'string' && english[key].length > 0, file + ': missing ' + key)
        checked++
      }
      ts.forEachChild(node, visit)
    }
    visit(source)
  }
  assert.ok(checked > 250)
  for (const key of ['确定', '取消操作', '确认离开', '继续编辑']) assert.ok(english[key].length <= 4, 'Taro modal button limit: ' + key)
})
