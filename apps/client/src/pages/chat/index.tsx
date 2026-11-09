import { t, uiNotice, useLocale, LanguageSwitch, syncPageLocale } from '../../i18n'
import Textarea from '../../components/AppTextarea'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Input, Text, View } from '@tarojs/components'
import Taro, { useReady, useDidShow } from '@tarojs/taro'
import { canSaveDraft, samePendingMessage } from '../../state'
import type { PendingMessage } from '../../state'
import ModelSettings from '../../components/ModelSettings'
import DemandPanel from '../../components/DemandPanel'
import SimulatedMarket from '../../components/SimulatedMarket'
import type { CollaborationController, LiveReply } from '../../components/DemandPanel'
import { strategyLabels } from '../../components/SolutionWorkspace'
import { allowsContinuous } from '../../continuous'
import { createRequestId } from '../../request-id'
import type { ContinuousConsent } from '../../continuous'
import type { DemandView } from '../../demand'
import { api, diagnosis, downloadJson, isH5, startSession } from '../../api'
import type { ChatMessage, ConfigList, Conversation, ConversationDetail, ModelConfig, Provider, MessageVersionReference } from '../../api'

let consentScopeSequence = 0
const nextConsentScope = () => 'conversation-scope-' + (++consentScopeSequence)

export default function ChatPage() {
  useLocale()
  useReady(syncPageLocale)
  useDidShow(syncPageLocale)
  const stickToBottom = useRef(true)
  useEffect(() => {
    if (!isH5) return
    const area = document.getElementById('chat-scroll')
    const update = () => { if (area) stickToBottom.current = area.scrollHeight - area.scrollTop - area.clientHeight < 160 }
    area?.addEventListener('scroll', update)
    return () => area?.removeEventListener('scroll', update)
  }, [])
  const [ready, setReady] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [page, setPage] = useState<'chat' | 'solution' | 'market'>('chat')
  const [split, setSplit] = useState(false)
  const [liveReply, setLiveReply] = useState<LiveReply | null>(null)
  const [workspaceDirty, setWorkspaceDirty] = useState(false)
  const [demandLoadError, setDemandLoadError] = useState<string | null>(null)
  const onDemandLoadError = useCallback((message: string | null) => setDemandLoadError(message), [])
  const navigationPrompt = useRef(false)
  const controller = useRef<CollaborationController | null>(null)
  const onController = useCallback((value: CollaborationController) => { controller.current = value }, [])
  const onStream = useCallback((value: LiveReply | null) => setLiveReply(value), [])
  const onDirtyChange = useCallback((value: boolean) => setWorkspaceDirty(value), [])
  const [providers, setProviders] = useState<Provider[]>([])
  const [configList, setConfigList] = useState<ConfigList>({ configs: [], active_id: null })
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState('')
  const [draftReference, setDraftReference] = useState<MessageVersionReference | null>(null)
  const referenceValue = useRef<MessageVersionReference | null>(null)
  function updateReference(value: MessageVersionReference | null) { referenceValue.current = value; setDraftReference(value) }
  const [busy, setBusy] = useState(false)
  const [loadingConversation, setLoadingConversation] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [rename, setRename] = useState<string | null>(null)
  const draftValue = useRef('')
  function updateDraft(value: string) { draftValue.current = value; setDraft(value) }
  const saveInFlight = useRef(false)
  const epoch = useRef(0)
  const queryEpoch = useRef(0)
  const pending = useRef<PendingMessage | null>(null)
  const conversationScope = useRef('')
  if (!conversationScope.current) conversationScope.current = nextConsentScope()
  const [continuousConsent, setContinuousConsent] = useState<ContinuousConsent | null>(null)
  const [autoParseMessageId, setAutoParseMessageId] = useState<string>()
  const [demandState, setDemandState] = useState<{ id: string; view: DemandView } | null>(null)
  const [aiOperation, setAiOperation] = useState<{ id: string; busy: boolean } | null>(null)
  const onDemandView = useCallback((id: string, view: DemandView) => setDemandState({ id, view }), [])
  const onDemandBusy = useCallback((id: string, value: boolean) => setAiOperation(previous => value || previous?.id === id ? { id, busy: value } : previous), [])
  const onAutoComplete = useCallback((id: string) => setAutoParseMessageId(previous => previous === id ? undefined : previous), [])
  const active = configList.configs.find(config => config.id === configList.active_id)
  const continuousSnapshot = useRef({ consent: continuousConsent, active, scope: conversationScope.current })
  continuousSnapshot.current = { consent: continuousConsent, active, scope: conversationScope.current }
  const continuousEnabled = allowsContinuous(continuousConsent, active, conversationScope.current)
  const aiBusy = !!detail && aiOperation?.id === detail.id && aiOperation.busy
  useEffect(() => {
    if (isH5 && stickToBottom.current) { const area = document.getElementById('chat-scroll'); if (area) area.scrollTop = area.scrollHeight }
  }, [liveReply, demandState, detail])
  const demandView = demandState?.id === detail?.id ? demandState?.view : null
  useEffect(() => { setContinuousConsent(null); setAutoParseMessageId(undefined) }, [active?.id, active?.model, active?.base_url, active?.verified_at])
  function resetConversationConsent() {
    conversationScope.current = nextConsentScope(); setContinuousConsent(null); setAutoParseMessageId(undefined); setDemandState(null); setLiveReply(null); setWorkspaceDirty(false); setDemandLoadError(null); updateReference(null); controller.current?.cancel(); controller.current = null
  }
  async function toggleContinuous() {
    if (continuousEnabled) { setContinuousConsent(null); setAutoParseMessageId(undefined); return }
    if (!active || !ready) return
    const selectedConfig = active; const scope = conversationScope.current
    const answer = await Taro.showModal({ confirmText: t('确定'), cancelText: t('取消操作'), title: t("启用本次对话的连续 AI 理解"), content: t("你后续保存的每条消息将自动发送给 ") + active.provider + '（' + active.base_url + t("），模型 ") + active.model + t("，可能产生API费用。上下文仅含本会话最多6条/6000字近期原文、当前草稿和已确认清单，以及本条消息明确引用的同会话方案版本详情，不包含其他会话。切换会话、切换模型或刷新页面后需重新授权；可随时关闭。AI只生成草稿，整份清单仍须你明确确认。是否启用？") })
    if (answer.confirm && scope === conversationScope.current) setContinuousConsent({ scope, configId: selectedConfig.id, model: selectedConfig.model, baseUrl: selectedConfig.base_url, verifiedAt: selectedConfig.verified_at, grantedAt: new Date().toISOString() })
  }
  function configurationSaved(config: ModelConfig, activeId: string | null) {
    setConfigList(previous => ({
      active_id: activeId,
      configs: [...previous.configs.filter(item => item.id !== config.id), config]
        .map(item => ({ ...item, is_active: item.id === activeId }))
    }))
    setSettingsOpen(false)
    setNotice(t("模型配置已保存，可以开始记录需求。"))
  }
  async function refreshConfigs() {
    setConfigList(await api<ConfigList>('/config/models'))
  }
  async function refreshHistory(search = query) {
    if (!ready) return
    const requestEpoch = ++queryEpoch.current
    const result = await api<{ conversations: Conversation[] }>('/conversations?limit=50&offset=0&query=' + encodeURIComponent(search))
    if (requestEpoch === queryEpoch.current) setConversations(result.conversations)
  }
  useEffect(() => {
    let alive = true
    void (async () => {
      try {
        await startSession()
        if (!alive) return
        setReady(true)
        const capture = (e: unknown) => { if (alive) setError(diagnosis(e)) }
        await Promise.all([
          api<{ providers: Provider[] }>('/config/providers').then(catalog => { if (alive) setProviders(catalog.providers) }).catch(capture),
          api<ConfigList>('/config/models').then(configs => { if (alive) { setConfigList(configs); if (!configs.active_id) setSettingsOpen(true) } }).catch(capture),
          api<{ conversations: Conversation[] }>('/conversations?limit=50&offset=0').then(history => { if (alive) setConversations(history.conversations) }).catch(capture)
        ])
      } catch (e) { if (alive) { setError(diagnosis(e)); setSettingsOpen(true) } }
    })()
    return () => { alive = false }
  }, [])
  async function allowLeaveComposer(): Promise<boolean> {
    if (navigationPrompt.current) return false
    if (saveInFlight.current) { setError(t("当前消息正在保存，请完成后再切换对话。")); setPage('chat'); return false }
    const original = draftValue.current
    const originalReference = referenceValue.current
    if (!original && !originalReference) return true
    const selection = epoch.current
    navigationPrompt.current = true
    try {
      const answer = await Taro.showModal({ title: t("保留未发送文字？"), content: t("输入框中有尚未发送的文字或方案引用。取消会保留全文和引用；选择离开会丢弃这些未发送内容，不会替你保存或发送给 AI。"), confirmText: t("确认离开"), cancelText: t("继续编辑") })
      return answer.confirm === true && selection === epoch.current && draftValue.current === original && referenceValue.current === originalReference
    } catch {
      if (selection === epoch.current) { setError(t("无法打开离开确认，已保留未发送文字，请稍后重试。")); setPage('chat') }
      return false
    } finally { navigationPrompt.current = false }
  }
  async function openConversation(id: string) {
    if (id === detail?.id && !loadingConversation) return
    if (workspaceDirty) { setError(t("工作区有未保存修改，请先保存、带回对话或放弃。")); setPage('solution'); return }
    if (!await allowLeaveComposer()) return
    const version = ++epoch.current
    resetConversationConsent()
    setLoadingConversation(true); setDetail(null)
    updateDraft(''); setError(''); setNotice(''); setRename(null); setPage('chat')
    try {
      const conversation = await api<ConversationDetail>('/conversations/' + id)
      if (epoch.current === version) { setDetail(conversation); setLoadingConversation(false) }
    } catch (e) { if (epoch.current === version) { setDetail(null); setLoadingConversation(false); setError(diagnosis(e)) } }
  }
  async function newConversation() {
    if (workspaceDirty) { setError(t("工作区有未保存修改，请先处理。")); setPage('solution'); return }
    if (!await allowLeaveComposer()) return
    resetToEmptyConversation()
  }
  function resetToEmptyConversation() {
    resetConversationConsent()
    epoch.current++; setLoadingConversation(false); setDetail(null); updateDraft(''); setError(''); setNotice(''); setRename(null); setPage('chat'); pending.current = null
  }
  async function send(content = draftValue.current) {
    if (workspaceDirty) { setError(t("工作区有未保存修改，请先处理后发送。")); setPage('solution'); return }
    if (!canSaveDraft(content) || saveInFlight.current || loadingConversation || aiBusy || !ready) return
    const selection = epoch.current
    const referenceVersionId = referenceValue.current?.id ?? null
    const sendConsent = continuousEnabled ? continuousConsent : null
    saveInFlight.current = true; setBusy(true); setError(''); setNotice('')
    try {
      let target = detail
      if (!target && samePendingMessage(pending.current, pending.current?.conversationId ?? '', content, referenceVersionId)) target = await api<ConversationDetail>('/conversations/' + pending.current!.conversationId)
      const messageId = target && samePendingMessage(pending.current, target.id, content, referenceVersionId)
        ? pending.current!.id : await createRequestId()
      if (selection !== epoch.current) return
      if (!target) target = await api<ConversationDetail>('/conversations', 'POST', { title: content.trim().slice(0, 40) })
      if (!samePendingMessage(pending.current, target.id, content, referenceVersionId)) {
        pending.current = { conversationId: target.id, content, id: messageId, referenceVersionId }
      }
      const receipt = await api<{ message: ChatMessage; duplicate: boolean }>('/conversations/' + target.id + '/messages', 'POST', { content, client_message_id: pending.current!.id, reference_version_id: referenceVersionId })
      const saved = await api<ConversationDetail>('/conversations/' + target.id)
      pending.current = null
      if (selection === epoch.current) {
        setDetail(saved); updateDraft(''); updateReference(null)
        const latestConsent = continuousSnapshot.current
        const latestUserId = saved.messages.filter(message => message.role === 'user').at(-1)?.id
        if (sendConsent && latestConsent.consent === sendConsent && allowsContinuous(sendConsent, latestConsent.active, latestConsent.scope) && latestUserId === receipt.message.id) { setAutoParseMessageId(receipt.message.id); setNotice(t("原文已保存，按本次对话授权继续理解；AI回复和新方案仍待你检查。")) }
        else setNotice(t("原文已保存到本机。可以手动理解，或启用本次对话的连续 AI 理解。"))
      }
      await refreshHistory().catch(reason => { if (selection === epoch.current) setError(t("原文已保存，历史列表暂未刷新。") + diagnosis(reason)) })
    } catch (e) { if (selection === epoch.current) setError(diagnosis(e) + t(" 原文仍在输入框中，可重试。")); else pending.current = null }
    finally { saveInFlight.current = false; setBusy(false) }
  }
  function returnToComposer() {
    if (isH5) {
      const composer = document.getElementById('conversation-composer')
      composer?.scrollIntoView({ block: 'center', behavior: 'auto' })
      composer?.querySelector('textarea')?.focus({ preventScroll: true })
    } else {
      void Taro.pageScrollTo({ selector: '#conversation-composer', duration: 0 })
        .catch(() => setNotice(t("请向上滚动到输入框继续对话。")))
    }
  }
  function composerKeyDown(event: KeyboardEvent) {
    if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey ||
      event.isComposing || event.keyCode === 229 || event.repeat) return
    event.preventDefault()
    void send((event.target as HTMLTextAreaElement).value)
  }
  const saveDisabled = !canSaveDraft(draft) || busy || loadingConversation || aiBusy || !ready
  async function renameConversation() {
    if (!detail || !rename?.trim()) return
    const id = detail.id; const selection = epoch.current
    try {
      const updated = await api<ConversationDetail>('/conversations/' + id, 'PATCH', { title: rename.trim() })
      if (epoch.current === selection) { setDetail(updated); setRename(null) }
      await refreshHistory()
    } catch (e) { setError(diagnosis(e)) }
  }
  async function removeConversation() {
    if (!detail) return
    const id = detail.id; const selection = epoch.current
    const answer = await Taro.showModal({ confirmText: t('确定'), cancelText: t('取消操作'), title: t("删除本地会话"), content: t("删除此会话和原文记录？此操作不删除模型配置，也不表示取消任何站外订单。") })
    if (!answer.confirm) return
    try { await api('/conversations/' + id, 'DELETE'); if (selection === epoch.current) resetToEmptyConversation(); await refreshHistory() }
    catch (e) { setError(diagnosis(e)) }
  }
  async function exportConversation(all = false) {
    if (!ready || !isH5 || (!all && !detail)) return
    try {
      const result = await api(all ? '/me/export' : '/conversations/' + detail!.id + '/export')
      downloadJson(result, all ? 'demand-search-history.json' : 'demand-search-conversation.json')
      setNotice(t("已导出本地会话，不包含 API Key。请自行妥善保管导出文件。"))
    } catch (e) { setError(diagnosis(e)) }
  }
  function feedbackToChat(text: string, reference: MessageVersionReference) {
    if (saveInFlight.current || loadingConversation || aiBusy) { setError(t("当前操作尚未完成，请稍后再加入修改意见。原文和引用保持不变。")); setPage('chat'); return false }
    if (referenceValue.current && referenceValue.current.id !== reference.id) { setError(t("输入框已引用版本 ") + referenceValue.current.number + t("。请先移除该引用，再选择其他版本；文字和工作区修改仍保留。")); setPage('chat'); return false }
    const combined = draftValue.current ? draftValue.current + '\n' + text : text
    if (combined.length > 8000) { setError(t("输入框已有文字，合并后超过上限。请先发送或缩短输入；工作区修改仍保留。")); return false }
    updateDraft(combined); updateReference({ id: reference.id, number: reference.number, status: reference.status })
    setError(''); setPage('chat'); setNotice(t("修改意见和版本引用已放入输入框，请检查后发送。不会自动确认或调用模型。"))
    setTimeout(returnToComposer, 0)
    return true
  }
  return <View className={'shell collaboration-shell' + (sidebarCollapsed ? ' sidebar-collapsed' : '')}>
    <View className='sidebar'>
      <View className='brand'><View className='brand-mark'>{t("需")}</View><Text>{t("需求端平台")}</Text></View>
      <Button className='new-chat' onClick={newConversation}>{t("＋ 新对话")}</Button>
      <Text className='section-label'>{t("历史对话")}</Text>
      <View className='history-search'><Input value={query} placeholder={t("搜索会话标题或内容")} onInput={e => setQuery(e.detail.value)} onConfirm={() => { void refreshHistory().catch(e => setError(diagnosis(e))) }} /><Button disabled={!ready} onClick={() => { void refreshHistory().catch(e => setError(diagnosis(e))) }}>{t("查找")}</Button></View>
      {!conversations.length && <View className='history-empty'><Text className='history-title'>{t("从一句“我想……”开始")}</Text><Text>{t("不必先想清全部条件。通过具体方案，一起发现真正的需要。")}</Text></View>}
      <View className='history-list'>{conversations.map(item => <Button key={item.id} className={'history-item' + (detail?.id === item.id ? ' selected' : '')} onClick={() => openConversation(item.id)}><Text>{item.title}</Text><Text className='history-date'>{item.message_count ?? 0}{t(" 条 · ")}{item.updated_at.slice(0, 10)}</Text></Button>)}</View>
      <Button className='secondary-button' disabled={!ready || !isH5} onClick={() => exportConversation(true)}>{t("导出全部历史")}</Button>
      <View className='sidebar-foot'><Text>{t("本机私人工作区")}</Text><Text>{t("原话、方案与确认分别保留")}</Text></View>
    </View>
    <View className='workspace'>
      <View className='toolbar'>
        <Button className='sidebar-toggle secondary-button' onClick={() => setSidebarCollapsed(!sidebarCollapsed)}>{sidebarCollapsed ? t("展开侧栏") : t("折叠侧栏")}</Button>
        <View className='page-tabs'><Button className={page === 'chat' && !split ? 'tab-active' : ''} onClick={() => { setPage('chat'); setSplit(false) }}>{t("AI 对话")}</Button><Button className={page === 'solution' && !split ? 'tab-active' : ''} onClick={() => { setPage('solution'); setSplit(false) }}>{t("方案工作区")}</Button><Button className={page === 'market' ? 'tab-active market-nav' : 'market-nav'} onClick={() => { setPage('market'); setSplit(false) }}>{t('模拟市场')}</Button><Button className={'split-toggle' + (split ? ' tab-active' : '')} onClick={() => { if (page === 'market') setPage('chat'); setSplit(!split) }}>{t("并排协作")}</Button></View>
        <LanguageSwitch /><Button className='settings-button' onClick={() => setSettingsOpen(true)}>{t("设置")}</Button>
      </View>
      <View className='task-bar'><Text className='task-name'>{detail?.title ?? t("新的需要")}</Text><Text className='mode-label'>{active ? active.model : t("AI 尚未配置")}</Text>{detail && <View className='compact-actions'><Button onClick={() => setRename(detail.title)}>{t("重命名")}</Button><Button onClick={() => exportConversation()}>{t("导出")}</Button><Button onClick={removeConversation}>{t("删除")}</Button></View>}</View>
      {rename !== null && <View className='rename-row'><Input value={rename} maxlength={120} placeholder={t("会话标题")} onInput={e => setRename(e.detail.value)} /><Button onClick={renameConversation}>{t("保存标题")}</Button><Button onClick={() => setRename(null)}>{t("取消")}</Button></View>}
      <View className={'collaboration-pages' + (split ? ' split-pages' : '')}>
        <View className={'chat-page' + (!split && page !== 'chat' ? ' pane-hidden' : '')}>
          <View className='chat-scroll' id='chat-scroll'>
            {!detail ? <View className='chat-welcome'><View className='eyebrow'><View className='status-dot' /><Text>{t("一起把想法变得具体")}</Text></View><Text className='headline'>{t("你想改善什么？")}</Text><Text className='subtitle'>{t("先给有价值的起点，再一起调整。无论是一个模糊想法、一份计划，还是已经明确的购物清单。")}</Text><View className='starter-directions'><Text>{t("讨论一个方案")}</Text><Text>{t("探索几个方向")}</Text><Text>{t("推进明确任务")}</Text></View></View> :
              <View className='messages'>{detail.messages.filter(message => message.role === 'user').map(message => <View className='conversation-turn' key={message.id}>
                <View className='message-bubble'><Text className='message-meta'>{t("你 · 原话已保存")}</Text><Text className='message-text' selectable>{message.content}</Text>{message.metadata?.reference_version && <Text className='message-reference field-help'>{t("引用版本 ")}{message.metadata.reference_version.number}（{message.metadata.reference_version.status === 'confirmed' ? t("已确认") : t("草稿")}{t("） · 已随原话保存")}</Text>}</View>
                {(demandView?.versions ?? []).filter(version => version.status === 'draft' && version.source_message_id === message.id).map(version => <View className='assistant-message' key={version.id}>
                  <Text className='message-meta'>AI · {version.model}{t(" · 方案版本 ")}{version.number}</Text>
                  {version.data.collaboration && <Text className='strategy-label'>{t(strategyLabels[version.data.collaboration.strategy])}</Text>}
                  <Text className='message-text assistant-reply' selectable>{version.data.assistant_reply || version.data.desired_outcome}</Text>
                  {version.data.clarification_questions.filter(question => !(version.data.assistant_reply ?? '').includes(question)).map((question, index) => <Text className='assistant-question' key={index}>{question}</Text>)}
                  <View className='compact-actions'><Button className='secondary-button view-workspace' onClick={() => { controller.current?.selectVersion(version.id); setPage('solution'); setSplit(false) }}>{t("查看方案与版本")}</Button><Button className='secondary-button reference-reply' onClick={() => feedbackToChat(t("针对版本 ") + version.number + t("，我想调整："), version)}>{t("提出修改")}</Button></View>
                </View>)}
                {liveReply?.messageId === message.id && <View className={'assistant-message stream-preview' + (liveReply.state === 'failed' ? ' stream-failed' : '')} aria-live='polite'>
                  <Text className='message-meta'>{liveReply.state === 'streaming' ? t("AI 正在回复 · 临时内容尚未保存") : t("回复中断 · 以下临时内容不是确认版本")}</Text><Text className='message-text' selectable>{liveReply.text || t("正在构思可供讨论的起点…")}</Text>{liveReply.error && <Text className='error-box'>{uiNotice(liveReply.error)}</Text>}
                </View>}
              </View>)}</View>}
          </View>
          <View className='chat-compose-area'>
            {notice && <Text className='notice-box'>{uiNotice(notice)}</Text>}{error && <Text className='error-box'>{uiNotice(error)}</Text>}
            {demandLoadError && <View className='demand-load-recovery'><Text className='error-box'>{t("方案暂未读取成功。")}{uiNotice(demandLoadError)}</Text><Button className='secondary-button reload-demand' disabled={aiBusy || undefined} onClick={() => controller.current?.refresh()}>{t("重新读取方案（不调用 AI）")}</Button></View>}
            <View className='continuous-mode'><Button className='secondary-button continuous-toggle' disabled={!active || !ready || undefined} onClick={() => { void toggleContinuous() }}>{continuousEnabled ? t("关闭连续 AI 理解") : t("启用连续 AI 理解")}</Button>
              {aiBusy ? <Button className='secondary-button stop-reply' onClick={() => controller.current?.cancel()}>{t("停止回复")}</Button> : detail && <Button className='secondary-button manual-reply' disabled={(!active || !detail.messages.length || !ready || !demandView || !!demandLoadError || demandView.demand?.status === 'withdrawn') || undefined} onClick={() => controller.current?.parse()}>{t("生成回复")}</Button>}
              <Text className='field-help'>{continuousEnabled ? t("本次对话已授权当前模型，可随时关闭。") : t("当前只保存到本机；启用后连续讨论方案。")}</Text>
            </View>
            <View className='composer' id='conversation-composer'>
              {draftReference && <View className='composer-reference'><Text className='field-help'>{t("待发送引用：版本 ")}{draftReference.number}（{draftReference.status === 'confirmed' ? t("已确认") : t("草稿")}）</Text><Text className='field-help'>{t("调用 AI 时会发送该版本详情；沿当前版本继续生成草稿，不会回滚或自动确认。")}</Text><Button className='secondary-button remove-reference' disabled={busy || aiBusy || undefined} onClick={() => { if (!saveInFlight.current && !aiBusy) { updateReference(null); setError(''); setNotice(t("已移除版本引用，输入框文字保留。只写版本号不会自动引用方案。")) } }}>{t("移除引用")}</Button></View>}
              <Textarea className='demand-input' value={draft} maxlength={8000} disabled={busy || loadingConversation || aiBusy || !ready} placeholder={t("说说你的想法，或对刚才的方案提一点修改…")} onInput={e => updateDraft(e.detail.value)} onBlur={e => updateDraft(e.detail.value)} confirmType='send' onConfirm={e => { if (!isH5) void send(e.detail.value) }} nativeProps={isH5 ? { onKeyDown: composerKeyDown } : undefined} />
              <View className='composer-bottom'><Text className='draft-note'>{continuousEnabled ? t("与 AI 讨论 · 不自动确认需求") : t("本地记录 · 未发送给 AI")}</Text><Button className='submit-button' disabled={saveDisabled || undefined} onClick={() => { void send() }}>{busy ? t("正在保存…") : aiBusy ? t("AI 正在回复…") : t("发送 ↗")}</Button></View>
            </View><Text className='composer-help'>{t("Enter 发送 · Shift+Enter 换行 · 原话与方案分开保存")}</Text>
            {!active && <Button className='setup-button' onClick={() => setSettingsOpen(true)}>{t("配置模型，开始 AI 对话")}</Button>}
          </View>
        </View>
        <View className={'solution-page' + (!split && page !== 'solution' ? ' pane-hidden' : '')}>
          <View className='solution-scroll' id='solution-scroll'>
            {detail && detail.messages.length > 0 ? <DemandPanel key={detail.id} conversationId={detail.id} latestMessageId={detail.messages.filter(message => message.role === 'user').at(-1)?.id} latestMessageReference={detail.messages.filter(message => message.role === 'user').at(-1)?.metadata?.reference_version ?? null} activeConfig={active} onNewConversation={newConversation} conversationScope={conversationScope.current} continuousConsent={continuousConsent} autoParseMessageId={autoParseMessageId} onAutoParseComplete={onAutoComplete} onViewChange={onDemandView} onBusyChange={onDemandBusy} onController={onController} onLoadError={onDemandLoadError} onStream={onStream} onFeedback={feedbackToChat} onDirtyChange={onDirtyChange} /> :
              <View className='workspace-welcome'><Text className='headline'>{t("想法会在这里变成方案")}</Text><Text className='subtitle'>{t("对话中形成的备选方向、步骤、预算假设和需求版本会同步到这里。你可以比较、修改，再决定是否确认。")}</Text><Button className='secondary-button' onClick={() => setPage('chat')}>{t("回到 AI 对话")}</Button></View>}
          </View>
        </View>
        {page === 'market' && <View className='market-page'><SimulatedMarket key={detail?.id ?? 'independent'} ready={ready} /></View>}
      </View>
      <View className='bottom-note'><Text>{ready ? t("本地服务已连接") : t("本地服务未连接")}</Text><Text>{page === 'market' ? t('本机虚构样本 · 无真实商品价格') : t('官方搜索入口 · 无商品价格数据')}</Text></View>
    </View>
    {settingsOpen && <ModelSettings providers={providers} configList={configList} ready={ready} onRefresh={refreshConfigs} onSaved={configurationSaved} onClose={() => setSettingsOpen(false)} />}
  </View>
}
