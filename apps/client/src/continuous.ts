import type { ModelConfig } from './api'
export type ContinuousConsent = { scope: string; configId: string; model: string; baseUrl: string; verifiedAt: string; grantedAt: string }
export function allowsContinuous(consent: ContinuousConsent | null | undefined, config: ModelConfig | undefined, scope: string): boolean {
  return !!consent && !!config && consent.scope === scope && consent.configId === config.id && consent.model === config.model &&
    consent.baseUrl === config.base_url && consent.verifiedAt === config.verified_at && !!consent.grantedAt
}
