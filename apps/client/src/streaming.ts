export type StreamEvent = { type: 'start' } | { type: 'delta'; text: string } | { type: 'complete'; view: unknown } | { type: 'error'; error: { code: string; message: string } }
export async function consumeNDJSON(body: ReadableStream<Uint8Array>, onEvent: (event: StreamEvent) => void): Promise<unknown> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let buffer = '', total = 0, replyLength = 0, terminal = false, started = false, result: unknown
  function line(raw: string) {
    if (!raw.trim()) return
    if (terminal) throw new Error('STREAM_TRAILING_DATA')
    const event = JSON.parse(raw) as StreamEvent
    if (event.type === 'start' && !started) { started = true; onEvent(event); return }
    if (!started) throw new Error('STREAM_START_MISSING')
    if (event.type === 'delta' && typeof event.text === 'string') {
      replyLength += event.text.length
      if (replyLength > 32000) throw new Error('STREAM_TOO_LARGE')
      onEvent(event); return
    }
    if (event.type === 'complete' && event.view && typeof event.view === 'object') { terminal = true; result = event.view; return }
    if (event.type === 'error' && typeof event.error?.code === 'string' && typeof event.error?.message === 'string') {
      onEvent(event); throw new Error('STREAM_SERVER_ERROR')
    }
    throw new Error('STREAM_INVALID_EVENT')
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      total += value.byteLength
      if (total > 8 * 1024 * 1024) throw new Error('STREAM_TOO_LARGE')
      buffer += decoder.decode(value, { stream: true })
      let end: number
      while ((end = buffer.indexOf('\n')) >= 0) { line(buffer.slice(0, end)); buffer = buffer.slice(end + 1) }
    }
    buffer += decoder.decode()
    if (buffer.trim()) line(buffer)
    if (!terminal) throw new Error('STREAM_INCOMPLETE')
    return result
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}
