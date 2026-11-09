import { test } from 'node:test'
import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import { uuidV4FromBytes, requestIdFrom } from '../src/request-id-core.ts'

test('UUID formatter uses exactly16 bytes, RFC v4/variant bits, lowercase and immutable input', () => {
  const input = Uint8Array.from({ length: 16 }, (_, i) => i)
  const original = input.slice()
  assert.equal(uuidV4FromBytes(input), '00010203-0405-4607-8809-0a0b0c0d0e0f')
  assert.deepEqual(input, original)
  assert.equal(uuidV4FromBytes(new Uint8Array(16).fill(255).buffer), 'ffffffff-ffff-4fff-bfff-ffffffffffff')
  assert.equal(uuidV4FromBytes(new Uint8Array(16)), '00000000-0000-4000-8000-000000000000')
})

test('UUID formatter rejects wrong sizes and objects pretending to be secure bytes', () => {
  for (const value of [undefined, null, '', [], Array(16).fill(1), new Uint8Array(0), new Uint8Array(15),
    new Uint8Array(17), new ArrayBuffer(32), new Uint16Array(8), { byteLength: 16 }]) {
    assert.throws(() => uuidV4FromBytes(value), { code: 'SECURE_RANDOM_UNAVAILABLE' })
  }
})

test('sync H5 entropy and async mini-program-shaped entropy produce valid UUIDs', async () => {
  const real = await requestIdFrom(() => webcrypto.getRandomValues(new Uint8Array(16)))
  assert.match(real, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  const synthetic = await requestIdFrom(async () => new Uint8Array(16).fill(7).buffer)
  assert.equal(synthetic, '07070707-0707-4707-8707-070707070707')
})

test('random-source failures and malformed bytes fail closed without fallback or secret detail', async () => {
  for (const source of [() => { throw new Error('synthetic private platform detail') },
    async () => { throw new Error('synthetic private platform detail') },
    () => null, async () => new Uint8Array(15)]) {
    let calls = 0
    await assert.rejects(requestIdFrom(() => { calls++; return source() }),
      error => error.code === 'SECURE_RANDOM_UNAVAILABLE' && error.message === 'SECURE_RANDOM_UNAVAILABLE')
    assert.equal(calls, 1)
  }
})

test('a nonresponsive platform random source times out without substitute entropy', async () => {
  let calls = 0
  await assert.rejects(requestIdFrom(() => { calls++; return new Promise(() => {}) }, 10),
    { code: 'SECURE_RANDOM_UNAVAILABLE' })
  assert.equal(calls, 1)
})
