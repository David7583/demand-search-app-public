export type Collaboration = {
  strategy: 'plan_first' | 'explore_first' | 'execute_first' | 'verify_first'; rationale: string
  task_type: 'planning' | 'exploration' | 'shopping' | 'general'; assumptions: string[]
  options: { option_id: string; title: string; summary: string; steps: string[]; tradeoffs: string[]; budget_estimate: null | { low: number; high: number; currency: string; basis: string; note: string } }[]
  next_steps: string[]; limitations: string[]; needs_verification: boolean
}
export type FactSource = 'user_explicit' | 'model_inferred' | 'user_confirmed' | 'unknown'
export type Readiness = 'exploring' | 'want' | 'need' | 'ready_to_purchase' | 'committed_elsewhere'
export type DemandFact = { text: string; source: FactSource; evidence: string; confirmed: boolean }
export type DemandBudget = { amount: number; currency: string; source: FactSource; evidence: string; confirmed: boolean }
export type DemandItem = {
  item_id: string; name: string; quantity: number | null; unit: string | null; source: FactSource; evidence: string; confirmed: boolean
  required: DemandFact[]; preferred: DemandFact[]; unknown: string[]; budget_ceiling: DemandBudget | null
  budget_basis: 'unit' | 'line_total' | 'unknown'; status: 'active' | 'removed'
}
export type DemandData = {
  assistant_reply?: string; collaboration?: Collaboration | null; solution_selection?: { option_id: string; status: 'user_selected' } | null; solution_confirmed?: boolean
  items?: DemandItem[]
  desired_outcome: string; required: DemandFact[]; preferred: DemandFact[]; unknown: string[]
  budget_ceiling: null | { amount: number; currency: string; source: FactSource; evidence: string; confirmed: boolean }
  readiness: Readiness; alternatives_acceptable: boolean | null; clarification_questions: string[]; possible_new_intent: boolean
}
export type DemandVersion = {
  id: string; demand_id: string; number: number; parent_version_id: string | null; source_message_id: string
  original_text: string; data: DemandData; status: 'draft' | 'confirmed'; model: string | null; provider: string | null; created_at: string; user_confirmed: boolean
}
export type DemandView = {
  demand: null | { id: string; intent_id: string; status: 'active' | 'withdrawn'; current_version_id: string; confirmed_version_id: string | null; ncp_revision: number }
  versions: DemandVersion[]; current_version: DemandVersion | null; confirmed_version: DemandVersion | null
}
export type DemandExport = { protocol: string; sharing_scope: 'private'; network_transmitted: false; packets: unknown[]; packet_utf8: string[]; sha256: string[] }
export const readinessOptions: { id: Readiness; label: string }[] = [
  { id: 'exploring', label: '探索中，先了解方案' }, { id: 'want', label: '有意愿' }, { id: 'need', label: '确有需要' },
  { id: 'ready_to_purchase', label: '准备购买（不是采购承诺）' }, { id: 'committed_elsewhere', label: '已在其他地方作出承诺' },
]
export const sourceLabels: Record<FactSource, string> = { user_explicit: '原话明确', model_inferred: 'AI 推断', user_confirmed: '用户填写或修改', unknown: '未知' }
