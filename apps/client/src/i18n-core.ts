import { english } from './translations.ts'
export type Locale = 'zh-CN' | 'en'
export const localeStorageKey = 'demand-search.interface-language'
export function normalizeLocale(value: unknown): Locale { return value === 'en' ? 'en' : 'zh-CN' }
export function translate(source: string, locale: Locale): string {
  return locale === 'en' && Object.hasOwn(english, source) ? english[source] : source
}
// Only application-authored notices/errors use this function. Never use it for
// original messages, model replies, requirement data, provider names or exports.
const errorMessages: Record<string, string> = {
  "INVALID_DEMAND_INPUT": "The original message is empty or exceeds the supported length.",
  "INVALID_DEMAND_CONTEXT": "The requirement context or referenced version is invalid. Select the reference again.",
  "CONTEXT_TOO_LARGE": "Context is too large or deeply nested. Send a new message without a version reference, or start a new conversation.",
  "KEY_IN_TEST_TEXT": "The text or context contains an API key. Remove it before sending.",
  "AI_SCHEMA_INVALID": "The model returned an invalid structured response. No new version was saved.",
  "AI_COLLABORATION_INVALID": "The model did not provide a valid actionable suggestion or required verification. Original text and existing versions are preserved; refine your request before retrying.",
  "AI_RESPONSE_TOO_LARGE": "The AI response exceeded the supported size.",
  "STREAM_CANCELLED": "Receiving stopped. Refresh the workspace to check whether a complete version was saved.",
  "DEMAND_STRUCTURE_INVALID": "The requirement structure is invalid. Existing versions are unchanged.",
  "DEMAND_WITHDRAWN": "This requirement was withdrawn. Start a new conversation instead.",
  "DEMAND_VERSION_CONFLICT": "The version changed. Review the latest version before retrying.",
  "MESSAGE_NOT_FOUND": "The original user message does not exist in this conversation.",
  "DEMAND_LIMIT_REACHED": "This requirement reached the version limit. Export it and start a new conversation.",
  "REQUEST_REPLACED": "The request was replaced during recovery. Refresh and review versions.",
  "AI_CONSENT_REQUIRED": "Explicit consent is required before sending this text and context to AI.",
  "CONFIRMATION_REQUIRED": "Explicit confirmation is required. This does not cancel external orders.",
  "PRIVATE_EXPORT_CONSENT_REQUIRED": "The export contains private original text. Confirm local export and keep the file secure.",
  "REQUEST_ID_CONFLICT": "This request ID belongs to different content or another conversation.",
  "REQUEST_IN_PROGRESS": "This request is still processing. Retry the same operation later.",
  "STALE_MESSAGE": "Use the latest original message to avoid replacing newer changes.",
  "DEMAND_EDIT_INVALID": "Check the edited fields and explicitly choose whether alternatives are acceptable.",
  "DEMAND_NOT_FOUND": "No requirement is available for confirmation.",
  "INTENT_CLARIFICATION_REQUIRED": "Confirm that this modifies the current requirement, or start another conversation.",
  "SOLUTION_CONFIRMATION_INVALID": "The plan confirmation value is invalid.",
  "SOLUTION_OPTION_UNKNOWN": "Select an option from this version.",
  "SOLUTION_SELECTION_REQUIRED": "Explicitly select the plan to adopt.",
  "SOLUTION_REQUIRES_VERIFICATION": "Essential conditions still need verification. The plan cannot be adopted yet.",
  "DEMAND_NOT_CONFIRMED": "No confirmed local intent is available. Review and confirm the requirements first.",
  "STALE_ANALYSIS": "A newer message arrived during analysis. Use the latest original text.",
  "REFERENCE_VERSION_NOT_FOUND": "That reference is not available in this conversation. Select a version again.",
  "SESSION_RATE_LIMITED": "Local sessions are being created too frequently. Please wait and retry.",
  "MODEL_CONFIG_NOT_FOUND": "The model configuration is missing or was deleted.",
  "API_MODE_UNSUPPORTED": "This provider does not support the selected API format.",
  "MODEL_KEY_FORMAT_INVALID": "The key must contain 8–4096 printable ASCII characters without spaces or line breaks.",
  "CREDENTIAL_IN_METADATA": "Do not put a key in the configuration name, address or model ID.",
  "MODEL_REQUIRED": "Select or enter a model ID.",
  "TEST_TEXT_REQUIRED": "Enter a requirement for the live parsing test.",
  "MODEL_NOT_CONFIGURED": "Configure and verify a model first.",
  "MODEL_KEY_REQUIRED": "Enter an API key in Settings.",
  "NEW_KEY_REQUIRED": "The provider or API address changed. Enter a key again; the previous key will not be forwarded.",
  "VALIDATION_EXPIRED": "Validation expired or was already used. Test again before saving.",
  "CONFIG_CHANGED": "The original configuration changed or was deleted. Test again.",
  "SEARCH_QUERY_TOO_LONG": "The name and confirmed conditions exceed 200 characters. Shorten them and confirm a new version.",
  "SEARCH_QUERY_INVALID": "Keywords contain unsupported control characters.",
  "SEARCH_ITEM_UNCONFIRMED": "Confirm the name of each item to search.",
  "EXTERNAL_LINK_INVALID": "The platform address is outside the fixed allowlist.",
  "SEARCH_ITEMS_INVALID": "The same item cannot be selected more than once.",
  "SEARCH_ITEMS_EMPTY": "The list has no searchable items.",
  "DEMAND_VERSION_NOT_FOUND": "This requirement version is not available in the conversation.",
  "DEMAND_CONFIRMATION_REQUIRED": "Review and confirm the list version first.",
  "SEARCH_ITEM_NOT_FOUND": "This historical requirement has no separate list items.",
  "PROVIDER_STREAM_INVALID": "The provider returned an invalid stream. No completed reply was saved and no automatic retry was made.",
  "PROVIDER_HOST_MISMATCH": "The hostname does not match this provider. For a compatible third-party service, select Custom and verify its address.",
  "PROVIDER_BUSY": "The local provider request limit was reached. Retry later.",
  "DNS_FAILED": "The provider hostname could not be resolved. Check its address and your connection.",
  "INVALID_BASE_URL": "Use a public HTTPS address on port 443 without credentials or query parameters.",
  "DNS_TIMEOUT": "Provider hostname resolution timed out.",
  "SSRF_BLOCKED": "The address resolves to a local or restricted network. No key was sent.",
  "PROVIDER_RESPONSE_TOO_LARGE": "The provider response exceeded the local safety limit.",
  "PROVIDER_STREAM_ERROR": "The provider interrupted generation. No automatic retry was made.",
  "PROVIDER_RESPONSE_INVALID": "The provider response is not supported JSON.",
  "AI_REFUSED": "The model declined this request. No reply was saved.",
  "AI_OUTPUT_INCOMPLETE": "Generation was truncated or filtered. No completed reply was saved.",
  "PROVIDER_REDIRECT_BLOCKED": "The provider redirect was blocked. No key was forwarded.",
  "TLS_VERIFY_FAILED": "Provider TLS certificate verification failed.",
  "PROVIDER_TIMEOUT": "The provider timed out. No automatic retry was made.",
  "PROVIDER_NETWORK_ERROR": "The provider connection was interrupted. No automatic retry was made.",
  "PROVIDER_STREAM_UNSUPPORTED": "This endpoint did not return a supported stream. Check the model and API compatibility. No second call was made automatically.",
  "CREDENTIAL_IN_RESPONSE": "The provider response contains credentials and was blocked from display.",
  "SECRET_STORAGE_UNAVAILABLE": "Secure local key storage currently requires Windows.",
  "SECRET_STORAGE_INVALID": "The encrypted key format is invalid.",
  "SECRET_STORAGE_FAILED": "Windows could not protect or decrypt the configuration. Use the original Windows user, or enter the key again.",
  "SECURE_RANDOM_UNAVAILABLE": "A secure request ID could not be generated. Nothing was sent. Retry using a supported local browser.",
  "PROVIDER_AUTH_FAILED": "The provider rejected authentication. Check the key and its permissions in Settings.",
  "PROVIDER_RATE_LIMITED": "The provider rate limit was reached. Wait before retrying.",
  "PROVIDER_MODEL_NOT_FOUND": "The provider could not find this model. Check the model ID and access permissions.",
  "PROVIDER_HTTP_ERROR": "The provider returned an HTTP error. Check its service status and configuration."
}
const noticePairs = Object.entries(english).filter(([zh, en]) => zh !== en && zh.length > 1 && en.length > 1)
export function translateNotice(message: string, locale: Locale): string {
  const direct = locale === 'en' ? (Object.hasOwn(english, message) ? english[message] : undefined) : noticePairs.find(([, en]) => en === message)?.[0]
  if (direct !== undefined) return direct
  const pairs = noticePairs.map(([zh, en]) => locale === 'en' ? [zh, en] : [en, zh]).sort((a, b) => b[0].length - a[0].length)
  // Single pass prevents a translated fragment from being translated again.
  let result = '', cursor = 0
  while (cursor < message.length) {
    const match = pairs.find(([from]) => message.startsWith(from, cursor))
    if (match) { result += match[1]; cursor += match[0].length }
    else { result += message[cursor]; cursor++ }
  }
  if (locale === 'en' && /[\u3400-\u9fff]/.test(result)) {
    const code = message.match(/\[([A-Z][A-Z0-9_]+)\]/)?.[1]
    if (code) return (errorMessages[code] ?? 'The operation was rejected. Check this diagnostic code before retrying.') + ' [' + code + ']'
  }
  return result
}
