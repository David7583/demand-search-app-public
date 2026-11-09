import { t, uiNotice, useLocale, LanguageSwitch } from '../i18n'
import Textarea from './AppTextarea'
import { useEffect, useRef, useState } from 'react'
import { Button, Checkbox, CheckboxGroup, Input, Label, Picker, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { api, diagnosis, isLocalConfigurationUi } from '../api'
import type { ConfigList, ModelConfig, Provider, Validation } from '../api'

type Props = { providers: Provider[]; configList: ConfigList; ready: boolean; onRefresh: () => Promise<void>; onClose: () => void; onSaved: (config: ModelConfig, activeId: string | null) => void }
export default function ModelSettings({ providers, configList, ready, onRefresh, onClose, onSaved }: Props) {
  useLocale()
  const [providerIndex, setProviderIndex] = useState(0)
  const [name, setName] = useState('')
  const [base, setBase] = useState('')
  const [mode, setMode] = useState('responses')
  const [model, setModel] = useState('')
  const [key, setKey] = useState('')
  const [existingId, setExistingId] = useState<string | undefined>()
  const [models, setModels] = useState<string[]>([])
  const [consent, setConsent] = useState(false)
  const [testText, setTestText] = useState(t("想找一把适合久坐、预算 1500 元以内的办公椅。"))
  const [validation, setValidation] = useState<Validation | null>(null)
  const [busy, setBusy] = useState('')
  const busyRef = useRef(false)
  function start(operation: string) { busyRef.current = true; setBusy(operation) }
  function finish() { busyRef.current = false; setBusy('') }
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const provider = providers[providerIndex]
  const permitted = ready && isLocalConfigurationUi()
  useEffect(() => {
    if (providers.length) { setBase(providers[0].default_base_url); setMode(providers[0].default_api_mode) }
  }, [providers])
  function invalidate() { setValidation(null); setNotice(''); setError('') }
  function chooseProvider(index: number) {
    if (busyRef.current || !permitted) return
    if (!providers[index]) return
    setProviderIndex(index); setBase(providers[index].default_base_url); setMode(providers[index].default_api_mode)
    setKey(''); setModel(''); setModels([]); setExistingId(undefined); setConsent(false); invalidate()
  }
  function edit(config?: ModelConfig) {
    if (busyRef.current || !permitted) return
    fillForm(config)
  }
  function fillForm(config?: ModelConfig) {
    invalidate(); setKey(''); setModels([]); setConsent(false)
    setExistingId(config?.id); setName(config?.name ?? '')
    const index = Math.max(0, providers.findIndex(p => p.id === config?.provider))
    setProviderIndex(index); setBase(config?.base_url ?? providers[index]?.default_base_url ?? '')
    setMode(config?.api_mode ?? providers[index]?.default_api_mode ?? 'responses'); setModel(config?.model ?? '')
  }
  function payload() {
    return { name: name || provider?.label || t("AI 配置"), provider: provider?.id, base_url: base, api_mode: mode, model, ...(key ? { api_key: key } : {}), ...(existingId ? { existing_id: existingId } : {}), consent, test_text: testText }
  }
  async function discover() {
    if (busyRef.current || !permitted || (!key && !existingId) || !provider) return
    start('discover'); setError(''); setNotice('')
    try {
      const result = await api<{ models: { id: string }[]; discovery_supported: boolean; note?: string }>('/config/models/discover', 'POST', payload())
      setModels(result.models.map(item => item.id))
      setNotice(result.note || (result.models.length ? t("模型列表来自服务商接口；实际可用性仍需测试。") : t("未返回可用列表，请手动填写模型 ID。")))
    } catch (e) { setError(diagnosis(e) + t(" 可手动填写模型 ID 后测试。")) }
    finally { finish() }
  }
  async function test() {
    if (busyRef.current || !permitted || !consent || !model.trim() || !testText.trim() || (!key && !existingId) || !provider) return
    start('test'); setError(''); setNotice(''); setValidation(null)
    try {
      const result = await api<Validation>('/config/models/test', 'POST', payload())
      setValidation(result); setKey(''); setNotice(t("真实调用与解析校验成功。尚未替换配置，请点击保存。"))
    } catch (e) { setError(diagnosis(e)) }
    finally { finish() }
  }
  async function save() {
    if (!validation || busyRef.current || !permitted) return
    start('save'); setError('')
    try {
      const saved = await api<{ config: ModelConfig; active_id: string | null }>('/config/models/save', 'POST', { validation_id: validation.validation_id, make_active: true })
      setKey(''); setValidation(null); setExistingId(undefined)
      // The successful save response is authoritative. A second list request
      // must not trap the user in setup after their configuration was saved.
      finish(); onSaved(saved.config, saved.active_id)
    } catch (e) { setError(diagnosis(e)); setValidation(null) }
    finally { finish() }
  }
  async function activate(id: string) {
    if (busyRef.current || !permitted || configList.active_id === id) return
    start('activate'); setError('')
    try { await api('/config/models/' + id + '/activate', 'POST'); await onRefresh(); setNotice(t("默认配置已切换。")) }
    catch (e) { setError(diagnosis(e)) } finally { finish() }
  }
  async function remove(config: ModelConfig) {
    if (busyRef.current || !permitted) return
    start('delete'); setError('')
    try {
      const answer = await Taro.showModal({ confirmText: t('确定'), cancelText: t('取消操作'), title: t("删除模型配置"), content: t("删除“") + config.name + t("”及其加密密钥？历史会话会保留。") })
      if (!answer.confirm) return
      await api('/config/models/' + config.id, 'DELETE'); await onRefresh(); if (existingId === config.id) fillForm(); setNotice(t("配置已删除，历史会话未受影响。"))
    }
    catch (e) { setError(diagnosis(e)) } finally { finish() }
  }
  function close() { if (!busyRef.current) { setKey(''); onClose() } }
  return <View className='modal-shade'>
    <View className='settings-panel config-panel'>
      <View className='settings-heading'><LanguageSwitch /><Text>{t("初始化与模型配置")}</Text><Button className='config-return-button' disabled={!!busy} onClick={close}>{t("返回主界面")}</Button></View>
      <Text className='field-help'>{t('切换界面语言不会翻译原话、AI 回复或搜索关键词。')}</Text>
      <Text className='settings-intro'>{t("配置你的 AI 后，可进行真实需求解析。密钥由 Windows 当前用户保护；应用不会将密钥存入浏览器存储。购物来源仍需另行授权。")}</Text>
      {!permitted && <Text className='error-box'>{t("请在本机浏览器打开 http://127.0.0.1:8000 配置。微信与开发服务器当前不接收密钥。")}</Text>}
      {configList.configs.length > 0 && <View className='saved-configs'>
        <Text className='section-label'>{t("已保存配置")}</Text>
        {configList.configs.map(config => <View className='saved-config' key={config.id}>
          <View><Text className='config-name'>{config.name}{config.is_active ? t(" · 当前默认") : ''}</Text><Text className='muted'>{config.model} · {config.key_mask}</Text><Text className='muted'>{t("上次验证 ")}{config.verified_at}</Text></View>
          <View className='compact-actions'><Button disabled={!!busy || !permitted} onClick={() => edit(config)}>{t("修改")}</Button><Button disabled={!!busy || config.is_active || !permitted} onClick={() => activate(config.id)}>{t("切换")}</Button><Button disabled={!!busy || !permitted} onClick={() => remove(config)}>{t("删除")}</Button></View>
        </View>)}
        <Button className='secondary-button' disabled={!!busy || !permitted} onClick={() => edit()}>{t("新增配置")}</Button>
      </View>}
      <View className='form-grid'>
        <View className='field'><Label for='config-name'>{t("配置名称")}</Label><Input id='config-name' value={name} maxlength={80} disabled={!!busy || !permitted} placeholder={t("例如：日常需求分析")} onInput={e => { setName(e.detail.value); invalidate() }} /></View>
        <View className='field'><Text>{t("AI 服务商")}</Text><Picker mode='selector' range={providers.map(p => t(p.label))} value={providerIndex} disabled={!!busy || !permitted} onChange={e => chooseProvider(Number(e.detail.value))}><View className='picker-value'>{provider ? t(provider.label) : t("等待本地服务")} ▾</View></Picker></View>
        <View className='field span-all'><Label for='api-base'>{t("API 地址")}</Label><Input id='api-base' value={base} maxlength={300} disabled={!!busy || !permitted} placeholder={t("https://服务商域名/v1")} onInput={e => { setBase(e.detail.value); setConsent(false); invalidate() }} /><Text className='field-help'>{t("密钥将发送到上述 HTTPS 服务商。改变地址后必须重新输入密钥。")}</Text></View>
        {permitted && <View className='field span-all'><Label for='api-key'>API Key</Label><Input id='api-key' password value={key} maxlength={4096} disabled={!!busy || !permitted} placeholder={existingId ? t("留空保留已有密钥；不会回填") : t("仅在本页输入，不保存到浏览器")} onInput={e => { setKey(e.detail.value); invalidate() }} /><Text className='field-help'>{existingId ? t("编辑已有配置：测试失败不会覆盖原配置。") : t("请勿把 Key 粘贴到聊天区或截图中。")}</Text></View>}
        <View className='field'><Text>{t("接口格式")}</Text><Picker mode='selector' range={['Responses', 'Chat Completions']} value={mode === 'responses' ? 0 : 1} disabled={!!busy || !permitted} onChange={e => { setMode(Number(e.detail.value) === 0 ? 'responses' : 'chat_completions'); invalidate() }}><View className='picker-value'>{mode === 'responses' ? 'Responses' : 'Chat Completions'} ▾</View></Picker></View>
        <View className='field'><Label for='model-id'>{t("模型 ID")}</Label><Input id='model-id' value={model} maxlength={200} disabled={!!busy || !permitted} placeholder={t("从接口选择，或手动填写")} onInput={e => { setModel(e.detail.value); invalidate() }} /></View>
      </View>
      <View className='inline-actions'><Button className='secondary-button' disabled={!!busy || !permitted || (!key && !existingId)} onClick={discover}>{busy === 'discover' ? t("正在获取…") : t("获取可用模型")}</Button>{models.length > 0 && <Picker mode='selector' range={models} disabled={!!busy || !permitted} onChange={e => { if (busyRef.current || !permitted) return; setModel(models[Number(e.detail.value)]); invalidate() }}><View className='picker-value'>{t("选择接口返回的模型 ▾")}</View></Picker>}</View>
      <View className='field'><Label for='test-demand'>{t("连接验证用的需求")}</Label><Textarea id='test-demand' className='test-demand' value={testText} maxlength={2000} disabled={!!busy || !permitted} onInput={e => { setTestText(e.detail.value); invalidate() }} /></View>
      <CheckboxGroup onChange={e => { if (busyRef.current || !permitted) return; setConsent(e.detail.value.includes('consent')); invalidate() }}><Label className='consent-row'><Checkbox value='consent' checked={consent} disabled={!!busy || !permitted} /><Text>{t("我同意将上述测试需求发送给所选服务商，可能产生 API 费用。只发送本次文本，不上传历史。")}</Text></Label></CheckboxGroup>
      {notice && <Text className='notice-box'>{uiNotice(notice)}</Text>}{error && <Text className='error-box'>{uiNotice(error)}</Text>}
      {validation && <View className='parse-result'><Text className='result-title'>{t("真实解析验证结果")}</Text><Text>{t("请求模型：")}{validation.result.requested_model}</Text><Text>{t("实际模型：")}{validation.result.actual_model}</Text><Text>{t("连接状态：")}{validation.result.connection_status} · {validation.result.tested_at}</Text><Text className='json-output' selectable>{JSON.stringify(validation.result.parsed, null, 2)}</Text><Text className='field-help'>{t("这是 AI 解析预览，不等于用户已确认或商品事实。验证凭据到期：")}{validation.expires_at}</Text></View>}
      <View className='form-actions'><Button className='secondary-button' disabled={!!busy || !permitted || !consent || !model.trim() || !testText.trim() || (!key && !existingId)} onClick={test}>{busy === 'test' ? t("正在真实调用，请稍候…") : t("测试连接并解析")}</Button><Button className='primary-button' disabled={!!busy || !validation || !permitted} onClick={save}>{busy === 'save' ? t("正在保存…") : t("保存并设为默认")}</Button></View>
      <Text className='settings-footnote'>{t("失败不会替换上次有效配置。配置保存在本机，仅供当前 Windows 用户使用。请勿将密钥发送到聊天或截图中。")}</Text>
    </View>
  </View>
}
