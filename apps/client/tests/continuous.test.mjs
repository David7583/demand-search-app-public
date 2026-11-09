import { test } from 'node:test'
import assert from 'node:assert/strict'
import { allowsContinuous } from '../src/continuous.ts'

const config = { id: 'test-config', model: 'synthetic', base_url: 'https://models.example.com/v1', verified_at: '2026-11-04T00:00:00Z' }
const consent = { scope: 'conversation-A', configId: config.id, model: config.model, baseUrl: config.base_url, verifiedAt: config.verified_at, grantedAt: '2026-11-04T01:00:00Z' }

test('continuous AI requires an explicit recorded grant for this conversation and exact configuration', () => {
  assert.equal(allowsContinuous(consent, config, 'conversation-A'), true)
  assert.equal(allowsContinuous(null, config, 'conversation-A'), false)
  assert.equal(allowsContinuous({ ...consent, grantedAt: '' }, config, 'conversation-A'), false)
  assert.equal(allowsContinuous(consent, config, 'conversation-B'), false)
  assert.equal(allowsContinuous(consent, undefined, 'conversation-A'), false)
  for (const [field, value] of [['id', 'other'], ['model', 'other'], ['base_url', 'https://other.example/v1'], ['verified_at', 'new-verification']]) {
    assert.equal(allowsContinuous(consent, { ...config, [field]: value }, 'conversation-A'), false)
  }
})
