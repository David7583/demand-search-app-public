import { test } from 'node:test'
import assert from 'node:assert/strict'
import { consumeNDJSON } from '../src/streaming.ts'
const encode = value => new TextEncoder().encode(value)
const stream = values => new ReadableStream({ start(controller) { for (const value of values) controller.enqueue(typeof value === 'string' ? encode(value) : value); controller.close() } })
const start = '{"type":"start"}\n'
const complete = '{"type":"complete","view":{"versions":[]}}\n'

test('NDJSON emits actual early deltas before a complete reply is available', async () => {
  let controller
  const body = new ReadableStream({ start(value) { controller = value } })
  const events = []
  let finished = false
  const pending = consumeNDJSON(body, event => events.push(event)).then(value => { finished = true; return value })
  controller.enqueue(encode(start + '{"type":"delta","text":"先给一个方案"}\n'))
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.equal(finished, false)
  assert.equal(events[1].text, '先给一个方案')
  controller.enqueue(encode(complete)); controller.close()
  assert.deepEqual(await pending, { versions: [] })
})

test('NDJSON preserves Chinese across arbitrary UTF8 and line chunk boundaries', async () => {
  const bytes = encode(start + '{"type":"delta","text":"方向甲\\n再讨论"}\n' + complete)
  const events = []
  const result = await consumeNDJSON(stream([...bytes].map(byte => Uint8Array.of(byte))), event => events.push(event))
  assert.equal(events[1].text, '方向甲\n再讨论')
  assert.deepEqual(result, { versions: [] })
})

test('NDJSON truncation and missing start never certify a stored version', async () => {
  await assert.rejects(consumeNDJSON(stream([start, '{"type":"delta","text":"部分"}\n']), () => {}), /STREAM_INCOMPLETE/)
  await assert.rejects(consumeNDJSON(stream([complete]), () => {}), /STREAM_START_MISSING/)
})

test('NDJSON rejects invalid events, duplicate completion, oversized previews and corrupt UTF8', async () => {
  for (const value of [
    start + '{"type":"delta","text":12}\n' + complete,
    start + complete + complete,
    start + '{"type":"delta","text":"' + 'x'.repeat(32001) + '"}\n',
  ]) await assert.rejects(consumeNDJSON(stream([value]), () => {}))
  await assert.rejects(consumeNDJSON(stream([encode(start), Uint8Array.of(0xff)]), () => {}))
})

test('NDJSON server errors preserve explicit diagnostics without returning partial success', async () => {
  const events = []
  await assert.rejects(consumeNDJSON(stream([start, '{"type":"error","error":{"code":"STALE_ANALYSIS","message":"版本已变更"}}\n']), event => events.push(event)), /STREAM_SERVER_ERROR/)
  assert.equal(events.at(-1).error.code, 'STALE_ANALYSIS')
})

test('NDJSON cancels source and releases reader after a parsing failure', async () => {
  let cancelled = false
  const body = new ReadableStream({ start(controller) { controller.enqueue(encode('invalid\n')) }, cancel() { cancelled = true } })
  await assert.rejects(consumeNDJSON(body, () => {}))
  assert.equal(cancelled, true)
  assert.equal(body.locked, false)
})
