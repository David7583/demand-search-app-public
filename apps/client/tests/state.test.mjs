import { test } from 'node:test'
import assert from 'node:assert/strict'
import { allowedCredentialOrigin, canSaveDraft, samePendingMessage } from '../src/state.ts'
const protectedSession = { credential_entry_allowed: true, secret_storage: 'windows_dpapi_current_user' }
test('secret entry requires protected bootstrap and local static origin', () => {
  assert.equal(allowedCredentialOrigin('http://127.0.0.1:8000', protectedSession), true)
  assert.equal(allowedCredentialOrigin('http://127.0.0.1:18000', protectedSession), true)
  for (const url of ['http://127.0.0.1:10086', 'https://external.example', 'http://127.0.0.1.evil.example:8000']) {
    assert.equal(allowedCredentialOrigin(url, protectedSession), false)
  }
  assert.equal(allowedCredentialOrigin('http://127.0.0.1:8000', {}), false)
})
test('draft boundaries preserve original text without accepting blank or huge input', () => {
  assert.equal(canSaveDraft('  actual original wording  '), true)
  assert.equal(canSaveDraft('  '), false)
  assert.equal(canSaveDraft('x'.repeat(8001)), false)
})
test('retry id can only be reused for the same conversation and exact text', () => {
  const pending = { conversationId: 'A', content: 'original', id: 'request-A' }
  assert.equal(samePendingMessage(pending, 'A', 'original'), true)
  assert.equal(samePendingMessage(pending, 'B', 'original'), false)
  assert.equal(samePendingMessage(pending, 'A', 'changed'), false)
  assert.equal(samePendingMessage(null, 'A', 'original'), false)
})


test('message retry includes the exact referenced version, including removal and replacement', () => {
  const pending = { conversationId: 'A', content: 'same wording', id: 'retry-id', referenceVersionId: 'version-1' }
  assert.equal(samePendingMessage(pending, 'A', 'same wording', 'version-1'), true)
  assert.equal(samePendingMessage(pending, 'A', 'same wording', 'version-2'), false)
  assert.equal(samePendingMessage(pending, 'A', 'same wording', null), false)
  assert.equal(samePendingMessage({ ...pending, referenceVersionId: null }, 'A', 'same wording'), true)
  assert.equal(samePendingMessage({ ...pending, referenceVersionId: undefined }, 'A', 'same wording', 'version-1'), false)
})
