export class SecureRandomUnavailable extends Error {
  readonly code = 'SECURE_RANDOM_UNAVAILABLE'
  constructor() { super('SECURE_RANDOM_UNAVAILABLE'); this.name = 'SecureRandomUnavailable' }
}

// This function formats bytes from an explicitly supplied secure platform source.
// It never generates substitute entropy or mutates the caller's buffer.
export function uuidV4FromBytes(value: unknown): string {
  let bytes: Uint8Array
  if (value instanceof Uint8Array) bytes = value
  else if (value instanceof ArrayBuffer) bytes = new Uint8Array(value)
  else throw new SecureRandomUnavailable()
  if (bytes.byteLength !== 16) throw new SecureRandomUnavailable()
  const copy = new Uint8Array(bytes)
  copy[6] = (copy[6] & 0x0f) | 0x40
  copy[8] = (copy[8] & 0x3f) | 0x80
  const hex = Array.from(copy, byte => byte.toString(16).padStart(2, '0')).join('')
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-')
}

export async function requestIdFrom(source: () => unknown | Promise<unknown>, timeoutMs = 5000): Promise<string> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const value = await Promise.race([
      Promise.resolve().then(source),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new SecureRandomUnavailable()), timeoutMs)
      }),
    ])
    return uuidV4FromBytes(value)
  } catch {
    // Do not disclose platform exception details and never fall back to weak randomness.
    throw new SecureRandomUnavailable()
  } finally { if (timer !== undefined) clearTimeout(timer) }
}
