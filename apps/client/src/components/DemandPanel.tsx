import { t, uiNotice, useLocale } from '../i18n'
import Textarea from './AppTextarea'
import { useEffect, useRef, useState } from 'react'
import { Button, Checkbox, CheckboxGroup, Input, Label, Picker, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { api, collaborate, diagnosis, downloadJson, isH5 } from '../api'
import type { ModelConfig, MessageVersionReference } from '../api'
import ShoppingListEditor, { itemEditor, itemEdits } from './ShoppingListEditor'
import type { ItemEditor } from './ShoppingListEditor'
import SearchSources from './SearchSources'
import { DemandMarketMatches } from './SimulatedMarket'
import SolutionWorkspace from './SolutionWorkspace'
export type CollaborationController = { parse: () => void; cancel: () => void; selectVersion: (id: string) => void; refresh: () => void }
export type LiveReply = { text: string; state: 'streaming' | 'failed' | 'complete'; messageId: string; error?: string }
import { allowsContinuous } from '../continuous'
import { createRequestId } from '../request-id'
import type { ContinuousConsent } from '../continuous'
import { readinessOptions, sourceLabels } from '../demand'
import type { DemandData, DemandExport, DemandVersion, DemandView } from '../demand'

type Props = { onLoadError?: (message: string | null) => void; onController?: (controller: CollaborationController) => void; onStream?: (reply: LiveReply | null) => void; onFeedback?: (text: string, reference: MessageVersionReference) => boolean; onDirtyChange?: (dirty: boolean) => void; conversationId: string; latestMessageId?: string; latestMessageReference?: MessageVersionReference | null; activeConfig?: ModelConfig; onNewConversation: () => void; conversationScope: string; continuousConsent?: ContinuousConsent | null; autoParseMessageId?: string; onAutoParseComplete?: (id: string) => void; onViewChange?: (conversationId: string, view: DemandView) => void; onBusyChange?: (conversationId: string, busy: boolean) => void }
type Editor = { desired: string; required: string; preferred: string; unknown: string; budget: string; currency: string; readiness: number; alternatives: number; items: ItemEditor[] }
const empty: Editor = { desired: '', required: '', preferred: '', unknown: '', budget: '', currency: 'CNY', readiness: 0, alternatives: 0, items: [] }
function toEditor(data: DemandData): Editor {
  return { items: (data.items ?? []).map(itemEditor), desired: data.desired_outcome, required: data.required.map(item => item.text).join('\n'), preferred: data.preferred.map(item => item.text).join('\n'),
    unknown: data.unknown.join('\n'), budget: data.budget_ceiling ? String(data.budget_ceiling.amount) : '', currency: data.budget_ceiling?.currency ?? 'CNY',
    readiness: Math.max(0, readinessOptions.findIndex(item => item.id === data.readiness)), alternatives: data.alternatives_acceptable === null ? 0 : data.alternatives_acceptable ? 1 : 2 }
}
const lines = (value: string) => value.split('\n').map(line => line.trim()).filter(Boolean)

export default function DemandPanel({ onLoadError, onController, onStream, onFeedback, onDirtyChange, conversationId, latestMessageId, latestMessageReference, activeConfig, onNewConversation, conversationScope, continuousConsent, autoParseMessageId, onAutoParseComplete, onViewChange, onBusyChange }: Props) {
  useLocale()
  const [dirty, setDirty] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [selectedOption, setSelectedOption] = useState<string | null>(null)
  const [confirmSolution, setConfirmSolution] = useState(false)
  const streamAbort = useRef<AbortController | null>(null)
  const [view, setView] = useState<DemandView | null>(null)
  const [loadedMessageId, setLoadedMessageId] = useState<string | undefined>()
  const autoAttempted = useRef(new Set<string>())
  const [selectedId, setSelectedId] = useState('')
  const [editor, setEditor] = useState<Editor>(empty)
  const [reviewed, setReviewed] = useState(false)
  const [continueIntent, setContinueIntent] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const epoch = useRef(0)
  const inFlight = useRef(false)
  const pending = useRef<{ operation: string; signature: string; id: string } | null>(null)
  const latestAccess = useRef({ activeConfig, continuousConsent, conversationScope })
  latestAccess.current = { activeConfig, continuousConsent, conversationScope }
  const base = '/conversations/' + conversationId + '/demand'
  const selected = view?.versions.find(version => version.id === selectedId) ?? view?.current_version ?? null
  const historical = !!selected && selected.id !== view?.current_version?.id
  const withdrawn = view?.demand?.status === 'withdrawn'
  const editable = !!selected && !historical && !withdrawn && !busy
  function adopt(next: DemandView) {
    setView(next); onViewChange?.(conversationId, next); setSelectedId(next.current_version?.id ?? '')
    setEditor(next.current_version ? toEditor(next.current_version.data) : empty)
    setReviewed(false); setContinueIntent(false); setDirty(false); setConfirmSolution(false); setSelectedOption(next.current_version?.data.solution_selection?.option_id ?? null)
  }
  useEffect(() => {
    const generation = ++epoch.current
    setView(null); setLoadedMessageId(undefined); setError(''); setNotice(''); onLoadError?.(null)
    void api<DemandView>(base).then(next => { if (epoch.current === generation) { adopt(next); setLoadedMessageId(latestMessageId); onLoadError?.(null) } })
      .catch(reason => {
        if (epoch.current !== generation) return
        const message = diagnosis(reason)
        setError(message); onLoadError?.(message)
        // A later read-only recovery must not replay the pending paid request.
        if (latestMessageId) { autoAttempted.current.add(latestMessageId); onAutoParseComplete?.(latestMessageId) }
      })
    return () => { epoch.current++; streamAbort.current?.abort() }
  }, [base, latestMessageId])
  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])
  useEffect(() => { onController?.({ parse: () => { void parse() }, cancel: () => streamAbort.current?.abort(), selectVersion, refresh: () => { void refresh() } }) })
  useEffect(() => { onBusyChange?.(conversationId, !!busy) }, [busy, conversationId, onBusyChange])
  useEffect(() => () => { onBusyChange?.(conversationId, false) }, [conversationId, onBusyChange])
  useEffect(() => {
    if (!autoParseMessageId || autoParseMessageId !== loadedMessageId || !view || !allowsContinuous(continuousConsent, activeConfig, conversationScope) || inFlight.current || autoAttempted.current.has(autoParseMessageId)) return
    autoAttempted.current.add(autoParseMessageId)
    void parse(true)
  }, [autoParseMessageId, loadedMessageId, view, activeConfig, continuousConsent, conversationScope])
  function selectVersion(id: string) {
    const version = view?.versions.find(value => value.id === id)
    if (!version) { setNotice(t("该版本尚未读取，请先刷新版本。不会自动生成新方案。")); return }
    select(version)
  }
  function select(version: DemandVersion) {
    if (inFlight.current) { setNotice(t("当前操作尚未完成，请稍后再查看历史版本。当前版本和编辑保持不变。")); return }
    if (dirty) { setNotice(t("请先确认、带回对话或放弃当前编辑，再切换版本。")); return }
    setSelectedOption(version.data.solution_selection?.option_id ?? null); setConfirmSolution(false);
    setSelectedId(version.id); setEditor(toEditor(version.data)); setReviewed(false); setContinueIntent(false); setError(''); setNotice('')
  }
  function change(field: keyof Editor, value: string | number | ItemEditor[]) {
    if (!editable) return
    setEditor(previous => ({ ...previous, [field]: value })); setReviewed(false); setDirty(true)
  }
  async function requestBody(operation: string, value: Record<string, unknown>) {
    const signature = JSON.stringify(value)
    if (!pending.current || pending.current.operation !== operation || pending.current.signature !== signature) pending.current = { operation, signature, id: await createRequestId() }
    return { ...value, request_id: pending.current.id }
  }
  function newDemand() { if (!inFlight.current) onNewConversation() }
  async function refresh() {
    if (inFlight.current || dirty) { setNotice(t("当前有未保存的编辑，请先处理后刷新。")); return }
    const generation = epoch.current
    inFlight.current = true; setBusy('refresh')
    if (latestMessageId) { autoAttempted.current.add(latestMessageId); onAutoParseComplete?.(latestMessageId) }
    try {
      const result = await api<DemandView>(base)
      if (epoch.current === generation) {
        adopt(result); setLoadedMessageId(latestMessageId); setError(''); onLoadError?.(null)
        setNotice(t("已重新读取当前需求版本，没有调用模型。"))
      }
    } catch (reason) {
      if (epoch.current === generation) { const message = diagnosis(reason); setError(message); onLoadError?.(message) }
    } finally { inFlight.current = false; setBusy('') }
  }
  async function parse(continuous = false) {
    if (dirty) { setError(t("请先处理工作区未保存的修改，再继续生成方案。")); return }
    if (inFlight.current || !latestMessageId || !activeConfig || !view || withdrawn) return
    if (continuous && !allowsContinuous(continuousConsent, activeConfig, conversationScope)) return
    autoAttempted.current.add(latestMessageId)
    onAutoParseComplete?.(latestMessageId)
    const generation = epoch.current
    inFlight.current = true; setBusy('parse'); setError(''); setNotice('')
    let streamed = ''; const streamMessageId = latestMessageId
    try {
      // A continuous call requires the explicit, in-memory consent recorded by the
      // chat enable modal, matching this conversation scope and exact model configuration.
      // Without it, manual analysis always asks for this specific transmission.
      if (!continuous) {
        const answer = await Taro.showModal({ confirmText: t('确定'), cancelText: t('取消操作'), title: t("发送有限上下文给 AI"), content: t("将最新原文、本会话最多6条/6000字近期原文、当前草稿和已确认清单，以及本条消息明确引用的同会话方案版本详情（") + (latestMessageReference ? t("版本 ") + latestMessageReference.number : t("本条消息未引用")) + t("）发送到 ") + activeConfig.base_url + t("，使用 ") + activeConfig.model + t("。不发送其他会话，可能产生API费用。继续？") })
        if (!answer.confirm || generation !== epoch.current) return
      } else if (!allowsContinuous(continuousConsent, activeConfig, conversationScope)) return
      const body = await requestBody('parse', { message_id: latestMessageId, expected_version_id: view.current_version?.id ?? null, consent: true, config_id: activeConfig.id })
      if (generation !== epoch.current) return
      // Platform entropy can be asynchronous. Recheck live props and the exact grant
      // after it completes, before any paid model request is sent.
      const latest = latestAccess.current
      const currentConfig = latest.activeConfig
      if (!currentConfig || currentConfig.id !== activeConfig.id || currentConfig.model !== activeConfig.model ||
          currentConfig.base_url !== activeConfig.base_url || currentConfig.provider !== activeConfig.provider ||
          currentConfig.api_mode !== activeConfig.api_mode || currentConfig.verified_at !== activeConfig.verified_at ||
          (continuous && (latest.continuousConsent !== continuousConsent ||
            !allowsContinuous(latest.continuousConsent, currentConfig, latest.conversationScope)))) {
        setNotice(t("配置或授权已变化，未发送本次解析。"))
        return
      }
      const controller = new AbortController(); streamAbort.current = controller
      onStream?.({ text: '', state: 'streaming', messageId: streamMessageId })
      const result = await collaborate<DemandView>(base + '/collaborate', body, controller.signal, event => {
        if (generation !== epoch.current || controller.signal.aborted) return
        if (event.type === 'delta') { streamed += event.text; onStream?.({ text: streamed, state: 'streaming', messageId: streamMessageId }) }
      })
      if (!result || !Array.isArray(result.versions)) throw new Error('Invalid demand view')
      pending.current = null
      if (generation === epoch.current) { adopt(result); onStream?.(null); setNotice(t("新方案已保存到工作区，已确认需求保持不变。")) }
    } catch (reason) { if (generation === epoch.current) { const message = diagnosis(reason); setError(message + t(" 原文与旧版本仍保留。")); onStream?.({ text: streamed, state: 'failed', messageId: streamMessageId, error: message }) } }
    finally { streamAbort.current = null; inFlight.current = false; setBusy(''); if (continuous && latestMessageId) onAutoParseComplete?.(latestMessageId) }
  }
  async function confirm() {
    if (inFlight.current || !editable || !selected || !reviewed || editor.alternatives === 0) return
    if (selected.data.possible_new_intent && !continueIntent) { setError(t("请明确这是当前需求的修改，或开启新对话。")); return }
    const amount = editor.budget.trim() ? Number(editor.budget) : null
    if (!editor.desired.trim() || (amount !== null && (!Number.isFinite(amount) || amount < 0 || amount > 1e12)) || (amount !== null && !/^[A-Z]{3}$/.test(editor.currency))) {
      setError(t("请填写目标，并检查预算上限及三位大写货币代码。留空预算表示未知。")); return
    }
    const generation = epoch.current
    inFlight.current = true; setBusy('confirm'); setError('')
    try {
      const edits = { items: itemEdits(editor.items), desired_outcome: editor.desired.trim(), required: lines(editor.required), preferred: lines(editor.preferred), unknown: lines(editor.unknown),
        budget_ceiling: amount === null ? null : { amount, currency: editor.currency }, readiness: readinessOptions[editor.readiness].id, alternatives_acceptable: editor.alternatives === 1 }
      const body = await requestBody('confirm', { version_id: selected.id, confirm: true, continue_current_intent: continueIntent, selected_option_id: selectedOption, confirm_solution: confirmSolution, edits })
      if (generation !== epoch.current) return
      const result = await api<DemandView>(base + '/confirm', 'POST', body)
      pending.current = null
      if (generation === epoch.current) { adopt(result); setNotice(t("已保存新的确认版本。旧版和原文未被覆盖；没有对外发送需求。")) }
    } catch (reason) { if (generation === epoch.current) setError((reason instanceof Error && reason.message.startsWith(t("请检查每项")) ? reason.message : diagnosis(reason)) + t(" 你的修改仍在表单中；版本冲突时请先核对再刷新。")) }
    finally { inFlight.current = false; setBusy('') }
  }
  async function withdraw() {
    if (inFlight.current || !view?.current_version || !view.confirmed_version || withdrawn) return
    const generation = epoch.current
    inFlight.current = true; setBusy('withdraw')
    try {
      const answer = await Taro.showModal({ confirmText: t('确定'), cancelText: t('取消操作'), title: t("撤回本地需求"), content: t("撤回后该需求不能继续修改或复活；原话和版本保留。此操作不会删除历史或取消任何站外订单。继续？") })
      if (!answer.confirm || generation !== epoch.current) return
      const body = await requestBody('withdraw', { expected_version_id: view.current_version.id, confirm: true, reason: '用户在本地应用明确撤回需求' })
      if (generation !== epoch.current) return
      const result = await api<DemandView>(base + '/withdraw', 'POST', body)
      pending.current = null
      if (generation === epoch.current) { adopt(result); setNotice(t("需求已在本地撤回。可以另开新对话表达新需求。")) }
    } catch (reason) { if (generation === epoch.current) setError(diagnosis(reason)) }
    finally { inFlight.current = false; setBusy('') }
  }
  async function exportNcp() {
    if (inFlight.current || !view?.confirmed_version || !isH5) return
    const generation = epoch.current
    inFlight.current = true; setBusy('export')
    try {
      const answer = await Taro.showModal({ confirmText: t('确定'), cancelText: t('取消操作'), title: t("导出私人需求"), content: t("导出文件包含原文和需求条件，请自行保管。仅生成本地文件，不发送到NCP节点；如自行分享，可能泄露私人内容。继续？") })
      if (!answer.confirm || generation !== epoch.current) return
      const result = await api<DemandExport>(base + '/export', 'POST', { acknowledge_private_export: true })
      if (generation === epoch.current) { downloadJson(result, 'demand-search-ncp-private.json'); setNotice(t("已导出本地NCP消息与校验摘要。未进行网络传输或生成送达回执。")) }
    } catch (reason) { if (generation === epoch.current) setError(diagnosis(reason)) }
    finally { inFlight.current = false; setBusy('') }
  }
  function feedbackFromEditor(prefix = '') {
    if (!selected) return
    let editedItems
    try { editedItems = itemEdits(editor.items) }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("清单字段无效，请检查数量、名称和预算。")); return }
    const feedback = prefix + (prefix ? '\n' : '') + t("对版本 ") + selected.number + t(" 的修改意见（尚未确认）：\n目标：") + editor.desired + t("\n必须满足：") + editor.required + t("\n偏好：") + editor.preferred + t("\n未知：") + editor.unknown + t("\n总预算：") + (editor.budget ? editor.currency + ' ' + editor.budget : t("未知")) + t("\n准备程度：") + t(readinessOptions[editor.readiness].label) + t("\n替代方案：") + (editor.alternatives === 0 ? t("未知") : editor.alternatives === 1 ? t("接受") : t("暂不接受")) + t("\n当前倾向方案：") + (selected.data.collaboration?.options.find(option => option.option_id === selectedOption)?.title ?? t("未选择")) + t("\n清单：") + JSON.stringify(editedItems)
    if (feedback.length > 8000) { setError(t("修改意见太长，请分次讨论或直接确认保存。")); return }
    if (onFeedback?.(feedback, selected) !== false) { setDirty(false); setReviewed(false); setConfirmSolution(false) }
  }
  function discuss(text: string) {
    if (dirty) feedbackFromEditor(text)
    else if (selected) onFeedback?.(text, selected)
  }
  return <View className='demand-panel'>
    <View className='demand-heading'><Text className='result-title'>{t("动态方案工作区")}</Text><Button className='secondary-button' disabled={!!busy} onClick={refresh}>{t("刷新版本")}</Button></View>
    <Text className='field-help'>{t("AI草稿不等于你的确认；来源声明不等于可验证的商品事实。准备购买也不构成采购承诺。")}</Text>
    <View className='inline-actions'><Button className='primary-button' disabled={!!busy || !latestMessageId || !activeConfig || !view || !!withdrawn} onClick={() => { void parse() }}>{busy === 'parse' ? t("正在理解需求…") : t("根据最新对话生成方案")}</Button>{!activeConfig && <Text className='field-help'>{t("请先在设置中配置模型；历史和已有版本仍可查看。")}</Text>}</View>
    {dirty && <View className='editing-notice'><Text>{t("有未保存修改。切换页面会保留；发送新消息前请先处理。")}</Text><View className='compact-actions'><Button className='secondary-button' onClick={() => feedbackFromEditor()}>{t("作为修改意见带回对话")}</Button><Button className='secondary-button' onClick={() => { if (selected) { setEditor(toEditor(selected.data)); setDirty(false); setConfirmSolution(false); setSelectedOption(selected.data.solution_selection?.option_id ?? null) } }}>{t("放弃未保存修改")}</Button></View></View>}
    {error && <Text className='error-box'>{uiNotice(error)}</Text>}{notice && <Text className='notice-box'>{uiNotice(notice)}</Text>}
    {withdrawn && <View className='withdrawn-notice'><Text>{t("本需求已撤回，不能继续修改。历史仍保留。")}</Text><Button className='secondary-button' onClick={newDemand}>{t("新建独立需求对话")}</Button></View>}
    {selected && view && <>
      <View className='version-tools'><Text className='version-status'>{t("版本 ")}{selected.number} · {selected.user_confirmed ? t("用户已确认") : t("AI草稿 · 待确认")}{historical ? t(" · 历史只读") : t(" · 当前版本")}</Text>
        <View className='version-list'>{view.versions.map(version => <Button key={version.id} className={'version-item' + (selected.id === version.id ? ' selected' : '')} disabled={!!busy} onClick={() => select(version)}>{t("版本 ")}{version.number} · {version.user_confirmed ? t("已确认") : t("草稿")}</Button>)}</View>
        {historical && view.current_version && <Button className='secondary-button' onClick={() => select(view.current_version!)}>{t("回到当前版本")}</Button>}
      </View>
      {historical && <Text className='field-help historical-context-note'>{t("引用历史版本继续讨论时，会提供该版详情，但仍沿当前方案追加新草稿，不会自动回滚或采纳。使用讨论或反馈按钮明确引用；只在文字中提到版本号不会自动引用。")}</Text>}
      <Text className='field-help'>{selected.created_at}{selected.model ? t(" · 实际模型：") + selected.model : t(" · 本地用户确认或修改")}</Text>
      <SolutionWorkspace version={selected} selectedOption={selectedOption} editable={editable} onSelect={id => { setSelectedOption(id); setConfirmSolution(false); setDirty(true); setReviewed(false) }} onFeedback={discuss} />
      <Button className='secondary-button requirement-details-toggle' onClick={() => setDetailsOpen(!detailsOpen)}>{detailsOpen ? t("收起需求与来源") : t("查看 / 编辑结构化需求")}</Button>
      <View className={'requirement-details' + (detailsOpen ? '' : ' pane-hidden')}>
      <View className='original-evidence'><Text className='section-label'>{t("本版本依据的原话（保留不变）")}</Text><Text className='message-text' selectable>{selected.original_text}</Text></View>
      {selected.data.clarification_questions.length > 0 && <View className='clarification-box'><Text className='result-title'>{t("需要澄清")}</Text>{selected.data.clarification_questions.map((question, index) => <Text key={index}>{index + 1}. {question}</Text>)}<Text className='field-help'>{t("可以在对话中补充后重新理解，也可以保留未知项，不把未知当作不满足。")}</Text></View>}
      {selected.data.possible_new_intent && !historical && !withdrawn && <View className='clarification-box'><Text>{t("这可能是一个新需求。可将相关物品加入当前清单，也可为无关目标开启独立对话。")}</Text><CheckboxGroup onChange={event => { if (!busy) setContinueIntent(event.detail.value.includes('continue')) }}><Label className='consent-row'><Checkbox value='continue' checked={continueIntent} disabled={!!busy} /><Text>{t("这是当前清单的补充或修改，确认后继续同一需求。")}</Text></Label></CheckboxGroup><Button className='secondary-button' disabled={!!busy} onClick={newDemand}>{t("作为新需求开启对话")}</Button></View>}
      <ShoppingListEditor key={selected.id} items={editor.items} original={selected.data.items ?? []} editable={editable} onChange={items => change('items', items)} />
      <View className='demand-editor'>
        <View className='field'><Label for='demand-goal'>{t("想达到的目标")}</Label><Textarea id='demand-goal' className='demand-field' value={editor.desired} maxlength={1000} disabled={!editable} onInput={event => change('desired', event.detail.value)} /></View>
        <View className='demand-columns'><View className='field'><Label for='demand-required'>{t("必须满足（每行一项）")}</Label><Textarea id='demand-required' className='demand-field' value={editor.required} maxlength={15000} disabled={!editable} onInput={event => change('required', event.detail.value)} /></View>
          <View className='field'><Label for='demand-preferred'>{t("偏好（每行一项）")}</Label><Textarea id='demand-preferred' className='demand-field' value={editor.preferred} maxlength={15000} disabled={!editable} onInput={event => change('preferred', event.detail.value)} /></View></View>
        <View className='field'><Label for='demand-unknown'>{t("仍然未知（每行一项，可保留）")}</Label><Textarea id='demand-unknown' className='demand-field' value={editor.unknown} maxlength={15000} disabled={!editable} onInput={event => change('unknown', event.detail.value)} /></View>
        <View className='demand-columns'><View className='field'><Label for='demand-budget'>{t("整份清单总预算上限（留空表示未知）")}</Label><Input id='demand-budget' type='digit' value={editor.budget} disabled={!editable} onInput={event => change('budget', event.detail.value)} /></View><View className='field'><Label for='demand-currency'>{t("货币代码")}</Label><Input id='demand-currency' value={editor.currency} maxlength={3} disabled={!editable} onInput={event => change('currency', event.detail.value.toUpperCase())} /></View></View>
        <View className='demand-columns'><View className='field'><Text>{t("准备程度")}</Text><Picker mode='selector' range={readinessOptions.map(item => t(item.label))} value={editor.readiness} disabled={!editable} onChange={event => change('readiness', Number(event.detail.value))}><View className='picker-value'>{t(readinessOptions[editor.readiness].label)} ▾</View></Picker></View>
          <View className='field'><Text>{t("是否接受替代方案")}</Text><View className='alternatives-options'><Button className={'alternatives-choice' + (editor.alternatives === 1 ? ' selected' : '')} disabled={!editable} onClick={() => change('alternatives', 1)}>{t("接受替代方案")}</Button><Button className={'alternatives-choice' + (editor.alternatives === 2 ? ' selected' : '')} disabled={!editable} onClick={() => change('alternatives', 2)}>{t("暂不接受替代方案")}</Button></View><Text className='field-help'>{editor.alternatives === 0 ? t("请明确选择后确认。") : editor.alternatives === 1 ? t("已选择：接受替代方案") : t("已选择：暂不接受替代方案")}</Text></View></View>
      </View>
      <View className='source-evidence'><Text className='section-label'>{t("本版本条件来源")}</Text>{[...selected.data.required, ...selected.data.preferred].map((fact, index) => <View key={index} className='source-row'><Text>{fact.text}</Text><Text className='source-label'>{t(sourceLabels[fact.source])}{fact.confirmed ? t(" · 你已确认该条件") : t(" · 未确认")}</Text>{fact.evidence && <Text className='field-help'>{t("依据：")}{fact.evidence}</Text>}</View>)}
        {selected.data.budget_ceiling && <Text className='field-help'>{t("预算来源：")}{t(sourceLabels[selected.data.budget_ceiling.source])}{selected.data.budget_ceiling.confirmed ? t(" · 你已确认") : t(" · 未确认")}</Text>}
      </View>
      </View>
      {!historical && !withdrawn && <>
        {selected.data.collaboration && (isH5 ? <label className='consent-row solution-reviewed native-consent'><input type='checkbox' checked={confirmSolution} disabled={!!busy || !selectedOption || selected.data.collaboration.strategy === 'verify_first'} onChange={event => { setConfirmSolution(event.currentTarget.checked); setDirty(true) }} /><span>{selected.data.collaboration.strategy === 'verify_first' ? t("关键条件尚未核实，当前不能采纳方案。") : t("我明确采纳所选方案。")}{t("此选择不核实其假设、估价或外部信息，也不授权购买或执行。")}</span></label> : <CheckboxGroup onChange={event => { setConfirmSolution(event.detail.value.includes('solution')); setDirty(true) }}><Label className='consent-row solution-reviewed'><Checkbox value='solution' checked={confirmSolution} disabled={!!busy || !selectedOption || selected.data.collaboration.strategy === 'verify_first'} /><Text>{t("我明确采纳所选方案。此选择不核实假设、估价或外部信息，也不授权购买或执行。")}</Text></Label></CheckboxGroup>)}
{isH5 ? <label className='consent-row demand-reviewed native-consent'><input type='checkbox' checked={reviewed} disabled={!!busy} onChange={event => setReviewed(event.currentTarget.checked)} /><span>{t("我已检查结构化需求和清单，未知项保持未知。保存为新的确认版本；方案只有单独勾选采纳才会确认。")}</span></label> : <CheckboxGroup onChange={event => { if (!busy) setReviewed(event.detail.value.includes('reviewed')) }}><Label className='consent-row demand-reviewed'><Checkbox value='reviewed' checked={reviewed} disabled={!!busy} /><Text>{t("我已检查结构化需求和清单，未知项保持未知。保存为新的确认版本；方案只有单独勾选采纳才会确认。")}</Text></Label></CheckboxGroup>}
        <Button className='primary-button demand-confirm' disabled={!!busy || !reviewed || editor.alternatives === 0 || (selected.data.possible_new_intent && !continueIntent)} onClick={confirm}>{busy === 'confirm' ? t("正在保存版本…") : t("确认并保存新版本")}</Button></>}
      <View className='inline-actions'><Button className='secondary-button' disabled={!!busy || !view.confirmed_version || !isH5} onClick={exportNcp}>{t("导出本地 NCP 消息")}</Button><Button className='secondary-button' disabled={!!busy || !view.confirmed_version || !!withdrawn} onClick={withdraw}>{t("撤回本地需求")}</Button></View>
      {selected.status === 'confirmed' && !withdrawn && <DemandMarketMatches key={conversationId + ':' + selected.id} conversationId={conversationId} version={selected} dirty={dirty} onDiscuss={discuss} />}
      {selected.status === 'confirmed' && !withdrawn && <SearchSources conversationId={conversationId} versionId={selected.id} />}
      <Text className='field-help'>{t("仅生成本地私人消息表示，wire 保持 ODIP/0.1.3-exp.1。没有发往网络，不代表跨实现互操作或生产安全已验证。")}</Text>
    </>}
    {view && !selected && <Text className='field-help'>{t("保存原文后进行理解，再检查草稿并确认。每次解析和确认都会保留新版本。")}</Text>}
  </View>
}
