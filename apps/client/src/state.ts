export type CredentialBootstrap = { credential_entry_allowed?: boolean; secret_storage?: string }
export function allowedCredentialOrigin(origin: string, bootstrap: CredentialBootstrap): boolean {
  try {
    const url = new URL(origin)
    return url.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(url.hostname) && url.port !== '10086' &&
      bootstrap.credential_entry_allowed === true && bootstrap.secret_storage === 'windows_dpapi_current_user'
  } catch { return false }
}
export function canSaveDraft(text: string): boolean { return text.trim().length > 0 && text.length <= 8000 }
export type PendingMessage = { conversationId: string; content: string; id: string; referenceVersionId?: string | null }
export function samePendingMessage(pending: PendingMessage | null, conversationId: string, content: string, referenceVersionId: string | null = null): boolean {
  return pending !== null && pending.conversationId === conversationId && pending.content === content && (pending.referenceVersionId ?? null) === referenceVersionId
}
