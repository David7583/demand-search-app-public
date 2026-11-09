import { useEffect, useRef, useState } from 'react'
import { Button, Input, Picker, Text, View } from '@tarojs/components'
import { api, diagnosis } from '../api'
import { t, uiNotice, useLocale } from '../i18n'
import type { MessageVersionReference } from '../api'

type Packet = Record<string, unknown>
export type SimulatedOffering = {
  id: string; merchant_id: string; merchant_name: string; merchant_name_en?: string
  name: string; name_en: string; category: string; category_label: string; category_label_en: string
  kind: 'goods' | 'service'; description: string; description_en: string
  price: { amount: number; currency: string; unit: string; unit_en: string; data_origin: 'synthetic' }
  specifications: Record<string, string | number>; lead_time_days: number
  region: string; region_en: string; data_origin: 'synthetic'
}
type Catalog = {
  kind: 'simulated_market'; data_origin: 'synthetic'; total_merchants: number; total_offerings: number
  total: number; page: number; page_size: number
  categories: { id: string; label: string; label_en: string }[]; items: SimulatedOffering[]
}
type Merchant = {
  id: string; name: string; name_en: string; description: string; description_en: string
  region: string; region_en: string; business_type: string; business_type_en: string
  offerings: SimulatedOffering[]; capability: Packet; data_origin: 'synthetic'
}
type Match = {
  offering: SimulatedOffering; reasons: string[]; reasons_en: string[]
  budget: { status: 'within' | 'over' | 'unknown' | 'not_provided'; note: string; note_en: string }
  unverified: string[]; unverified_en: string[]; proposal: Packet
}
export type SimulatedMatches = {
  kind: 'simulated_market_matches'; data_origin: 'synthetic'; version_id: string; version_number: number
  intent_id: string; network_searched: false
  items: { item_id: string | null; name: string; matches: Match[]; unmatched_reason: string | null; unmatched_reason_en: string | null }[]
}
const budgetLabels = { within: '模拟价格在预算内', over: '模拟价格超出预算', unknown: '预算无法判定', not_provided: '未提供预算' }

function JsonView({ value, label }: { value: Packet; label: string }) {
  const [open, setOpen] = useState(false)
  return <View className='market-json'><Button className='secondary-button market-json-toggle' onClick={() => setOpen(!open)}>{open ? t('收起 JSON') : label}</Button>
    {open && <Text className='market-json-content' selectable>{JSON.stringify(value, null, 2)}</Text>}
  </View>
}
function Offering({ value }: { value: SimulatedOffering }) {
  const en = useLocale() === 'en'
  return <>
    <Text className='market-badge'>{t('虚构样本')}</Text>
    <Text className='config-name'>{en ? value.name_en : value.name}</Text>
    <Text className='field-help'>{en ? value.merchant_name_en ?? value.merchant_name : value.merchant_name} · {en ? value.category_label_en : value.category_label}</Text>
    <Text className='market-price'>{t('模拟价格：')}{value.price.currency} {value.price.amount} / {en ? value.price.unit_en : value.price.unit}</Text>
    <Text className='market-description'>{en ? value.description_en : value.description}</Text>
    <Text className='field-help'>{t('虚构属性：')}{Object.entries(value.specifications).map(([key, item]) => key + ': ' + item).join(' · ')}</Text>
    <Text className='field-help'>{en ? value.region_en : value.region} · {t('模拟交付天数：')}{value.lead_time_days}</Text>
  </>
}
export default function SimulatedMarket({ ready }: { ready: boolean }) {
  const en = useLocale() === 'en'
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [merchant, setMerchant] = useState<Merchant | null>(null)
  const [busy, setBusy] = useState(false)
  const [detailBusy, setDetailBusy] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const detailGeneration = useRef(0)
  const applied = useRef({ query: '', category: '' })
  useEffect(() => {
    if (ready) void search('', '', 1)
    return () => { generation.current++; detailGeneration.current++ }
  }, [ready])
  async function search(term: string, group: string, page: number) {
    const request = ++generation.current
    detailGeneration.current++; setMerchant(null); setDetailBusy(false)
    setBusy(true); setError('')
    try {
      const result = await api<Catalog>('/simulated-market?query=' + encodeURIComponent(term) + '&category=' + encodeURIComponent(group) + '&page=' + page + '&page_size=12')
      if (result.kind !== 'simulated_market' || result.data_origin !== 'synthetic' || !Array.isArray(result.items) || result.items.length > 12) throw new Error('Invalid simulated catalog')
      if (generation.current === request) { setCatalog(result); applied.current = { query: term, category: group } }
    } catch (reason) { if (generation.current === request) { setCatalog(null); setError(diagnosis(reason)) } }
    finally { if (generation.current === request) setBusy(false) }
  }
  async function showMerchant(id: string) {
    const request = ++detailGeneration.current
    setMerchant(null); setDetailBusy(true); setError('')
    try {
      const result = await api<Merchant>('/simulated-market/merchants/' + encodeURIComponent(id))
      if (result.id !== id || result.data_origin !== 'synthetic') throw new Error('Invalid simulated merchant')
      if (detailGeneration.current === request) setMerchant(result)
    } catch (reason) { if (detailGeneration.current === request) setError(diagnosis(reason)) }
    finally { if (detailGeneration.current === request) setDetailBusy(false) }
  }
  const categories = [{ id: '', label: t('全部分类'), label_en: t('全部分类') }, ...(catalog?.categories ?? [])]
  return <View className='simulated-market'>
    <Text className='headline'>{t('模拟市场')}</Text>
    <Text className='field-help market-disclaimer'>{t('商家、商品、服务、价格和属性均为本机生成的虚构样本，不是真实报价或搜索结果。无需模型 Key。')}</Text>
    {catalog && <Text className='market-count'>{catalog.total_merchants} {t('家虚构商家')} · {catalog.total_offerings} {t('项模拟商品与服务')}</Text>}
    <View className='market-search-row'>
      <Input className='market-query' value={query} maxlength={200} placeholder={t('搜索模拟商品、服务或商家')} onInput={event => setQuery(event.detail.value)} onConfirm={() => { if (ready) void search(query, category, 1) }} />
      <Picker mode='selector' range={categories.map(item => en ? item.label_en : item.label)} value={Math.max(0, categories.findIndex(item => item.id === category))} disabled={!ready || busy} onChange={event => { const id = categories[Number(event.detail.value)].id; setCategory(id); void search(query, id, 1) }}><View className='picker-value'>{en ? categories.find(item => item.id === category)?.label_en : categories.find(item => item.id === category)?.label} ▾</View></Picker>
      <Button className='secondary-button market-search-button' disabled={!ready || busy || undefined} onClick={() => search(query, category, 1)}>{busy ? t('正在查询…') : t('查询模拟市场')}</Button>
    </View>
    {error && <Text className='error-box'>{uiNotice(error)}</Text>}
    {detailBusy && <Text className='field-help'>{t('正在读取商家…')}</Text>}
    {merchant && <View className='market-merchant'>
      <View className='demand-heading'><Text className='result-title'>{en ? merchant.name_en : merchant.name}</Text><Button className='secondary-button market-close-merchant' onClick={() => { detailGeneration.current++; setMerchant(null) }}>{t('关闭详情')}</Button></View>
      <Text className='market-badge'>{t('虚构商家')}</Text><Text>{en ? merchant.description_en : merchant.description}</Text>
      <Text className='field-help'>{en ? merchant.business_type_en : merchant.business_type} · {en ? merchant.region_en : merchant.region}</Text>
      <JsonView key={merchant.id} value={merchant.capability} label={t('查看 NCP Capability JSON')} />
      <View className='market-grid'>{merchant.offerings.map(item => <View className='market-offering' key={item.id}><Offering value={item} /></View>)}</View>
    </View>}
    {catalog && <>
      <Text className='field-help'>{catalog.total} {t('项匹配样本')} · {t('第 ')}{catalog.page} / {Math.max(1, Math.ceil(catalog.total / catalog.page_size))}</Text>
      {!catalog.items.length && <Text className='notice-box'>{t('没有匹配的模拟样本。试试其他关键词或分类；这不代表真实市场没有供应。')}</Text>}
      <View className='market-grid market-catalog' aria-busy={busy}>{catalog.items.map(item => <View className='market-offering' key={item.id}><Offering value={item} /><Button className='secondary-button market-merchant-button' disabled={busy || undefined} onClick={() => showMerchant(item.merchant_id)}>{t('商家详情与 NCP')}</Button></View>)}</View>
      <View className='market-pagination'><Button className='secondary-button market-prev' disabled={busy || catalog.page <= 1 || undefined} onClick={() => search(applied.current.query, applied.current.category, catalog.page - 1)}>{t('上一页')}</Button><Button className='secondary-button market-next' disabled={busy || catalog.page * catalog.page_size >= catalog.total || undefined} onClick={() => search(applied.current.query, applied.current.category, catalog.page + 1)}>{t('下一页')}</Button></View>
    </>}
  </View>
}

export function DemandMarketMatches({ conversationId, version, dirty, onDiscuss }: { conversationId: string; version: MessageVersionReference; dirty: boolean; onDiscuss: (text: string) => void }) {
  const en = useLocale() === 'en'
  const [result, setResult] = useState<SimulatedMatches | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const inFlight = useRef(false)
  useEffect(() => { generation.current++; setResult(null); setBusy(false); setError(''); inFlight.current = false; return () => { generation.current++ } }, [conversationId, version.id])
  async function match() {
    if (inFlight.current || version.status !== 'confirmed') return
    const request = ++generation.current
    inFlight.current = true; setBusy(true); setError(''); setResult(null)
    try {
      const response = await api<SimulatedMatches>('/conversations/' + conversationId + '/demand/simulated-market', 'POST', { version_id: version.id })
      if (response.kind !== 'simulated_market_matches' || response.data_origin !== 'synthetic' || response.version_id !== version.id || response.network_searched !== false || !Array.isArray(response.items) || response.items.length > 30) throw new Error('Invalid simulated matches')
      if (generation.current === request) setResult(response)
    } catch (reason) { if (generation.current === request) setError(diagnosis(reason)) }
    finally { if (generation.current === request) { inFlight.current = false; setBusy(false) } }
  }
  return <View className='demand-market-matches'>
    <Text className='result-title'>{t('查询模拟市场')}</Text>
    <Text className='field-help'>{t('使用已保存的确认版本 ')}{version.number}{t('，逐项匹配本机虚构样本。不会调用 AI、确认方案或购买。')}</Text>
    {dirty && <Text className='editing-notice'>{t('表单有未保存修改；此次查询仍使用已保存版本，不包含这些修改。')}</Text>}
    <Button className='secondary-button market-match-button' disabled={busy || undefined} onClick={match}>{busy ? t('正在查询…') : t('查找模拟候选')}</Button>
    {error && <Text className='error-box'>{uiNotice(error)}</Text>}
    {result && <>
      <Text className='field-help'>{t('匹配线索仅来自虚构目录；未知条件不等于已满足。模拟预算判断不代表真实可购买或整份清单总价。')}</Text>
      {!result.items.length && <Text className='notice-box'>{t('该版本没有可匹配的清单项，可返回对话补充。')}</Text>}
      {result.items.map((item, index) => <View className='market-match-item' key={item.item_id ?? String(index)}>
        <Text className='result-title'>{index + 1}. {item.name}</Text>
        {!item.matches.length && <Text className='field-help'>{(en ? item.unmatched_reason_en : item.unmatched_reason) || t('暂无模拟候选')}</Text>}
        <View className='market-grid'>{item.matches.map(candidate => <View className='market-offering market-candidate' key={candidate.offering.id}>
          <Offering value={candidate.offering} />
          <Text className='market-clue'>{t('匹配线索：')}{(en ? candidate.reasons_en : candidate.reasons).join('；') || t('暂无')}</Text>
          <Text className='field-help'>{t('未知条件：')}{(en ? candidate.unverified_en : candidate.unverified).join('；') || t('暂无')}</Text>
          <Text className={'market-budget budget-' + candidate.budget.status}>{t(budgetLabels[candidate.budget.status])}</Text><Text className='field-help'>{en ? candidate.budget.note_en : candidate.budget.note}</Text>
          <JsonView value={candidate.proposal} label={t('查看 NCP Proposal JSON')} />
          <Button className='secondary-button market-discuss' onClick={() => onDiscuss(t('讨论模拟候选：') + item.name + ' → ' + (en ? candidate.offering.name_en : candidate.offering.name) + ' [' + candidate.offering.id + ']' + t('。这是虚构样本，请继续核实条件。'))}>{t('带回对话讨论')}</Button>
        </View>)}</View>
      </View>)}
    </>}
  </View>
}
