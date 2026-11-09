import { t, uiNotice, useLocale } from '../i18n'
import { useEffect, useRef, useState } from 'react'
import { Button, Input, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { api, diagnosis, isH5 } from '../api'
import { buildFallbackSearchLink, externalSearchTarget } from '../external-links'
import type { SearchSource } from '../external-links'

type SearchItem = { item_id: string | null; name: string; query: string; sources: SearchSource[]; query_notes?: string[]; query_notes_en?: string[] }
type SearchPlan = { kind: 'external_search_plan'; version_id: string; network_searched: false; offers: unknown[]; items: SearchItem[]; limitations: string[]; sourceCoverageNote: string; sourceCoverageNote_en?: string; limitations_en?: string[] }
type Props = { conversationId: string; versionId: string }
export default function SearchSources({ conversationId, versionId }: Props) {
  const locale = useLocale()
  const [market, setMarket] = useState<'CN' | 'international' | 'all'>('CN')
  const label = (source: SearchSource) => locale === 'en' ? source.label_en ?? source.label : source.label
  const [plan, setPlan] = useState<SearchPlan | null>(null)
  const [queries, setQueries] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const generation = useRef(0)
  const inFlight = useRef(false)
  useEffect(() => { generation.current++; setPlan(null); setQueries({}); setBusy(false); setError(''); setNotice(''); return () => { generation.current++ } }, [conversationId, versionId])
  async function prepare() {
    if (inFlight.current) return
    const selected = generation.current
    inFlight.current = true; setBusy(true); setError('')
    try {
      const result = await api<SearchPlan>('/conversations/' + conversationId + '/demand/search-plan', 'POST', { version_id: versionId })
      if (result.kind !== 'external_search_plan' || result.version_id !== versionId || result.network_searched !== false ||
          !Array.isArray(result.offers) || result.offers.length || !Array.isArray(result.items) || result.items.length > 30) throw new Error('Invalid plan')
      if (selected === generation.current) { setPlan(result); setQueries({}) }
    } catch (reason) { if (selected === generation.current) setError(diagnosis(reason)) }
    finally { inFlight.current = false; if (selected === generation.current) setBusy(false) }
  }
  async function copy(value: string, label: string): Promise<boolean> {
    const selected = generation.current
    try {
      await Taro.setClipboardData({ data: value })
      if (selected === generation.current) setNotice(label + t("已复制。请在原平台或浏览器使用。"))
      return true
    } catch {
      if (selected === generation.current) setNotice(t("未能访问剪贴板，请手动复制下方内容。"))
      return false
    }
  }
  function targetFor(source: SearchSource, item: SearchItem, query: string): string | null {
    return externalSearchTarget(source, item.query) ? buildFallbackSearchLink(source.id, query) : null
  }
  async function navigate(source: SearchSource, item: SearchItem, query: string) {
    const target = targetFor(source, item, query)
    if (!target) { setError(t("搜索入口或关键词校验失败，未打开外部地址。")); return }
    const selected = generation.current
    const answer = await Taro.showModal({ confirmText: t('确定'), cancelText: t('取消操作'),
      title: t("去原平台继续搜索"),
      content: t("将关键词“") + query + t("”发送到") + label(source) + t("官方搜索页，不发送会话全文。关键词可能包含你的私人条件，请先检查。预算和硬约束只是搜索文字，不保证平台执行筛选。平台可能要求登录；应用没有获取商品或价格。")
    })
    if (!answer.confirm || selected !== generation.current) return
    if (isH5) {
      window.open(target, '_blank', 'noopener,noreferrer')
      setNotice(t("已请求打开原平台搜索页；可能需要登录。如未打开，可复制链接后在浏览器打开。"))
    } else {
      setNotice(t("LINK_UNSUPPORTED_ON_PLATFORM：当前小程序未启用外部网页跳转，未做真机验证。可复制链接后在浏览器打开。"))
    }
  }
  return <View className='search-sources'>
    <Text className='result-title'>{t("去原平台继续搜索")}</Text>
    <View className='market-filter' role='group' aria-label={t('搜索市场')}>
      {([{ id: 'CN', label: '中国平台' }, { id: 'international', label: '海外平台' }, { id: 'all', label: '全部平台' }] as const).map(option => <Button key={option.id} className={'secondary-button market-option' + (market === option.id ? ' selected' : '')} aria-pressed={market === option.id} onClick={() => setMarket(option.id)}>{t(option.label)}</Button>)}
    </View>
    {market !== 'CN' && <Text className='field-help international-note'>{t('海外入口使用原关键词；可自行填写英文，不自动翻译、换汇或保证跨境配送。')}</Text>}
    <Text className='field-help'>{t("入口按所选已确认版本生成，表单未确认的修改不计入。本版本不接商品或联盟 API，不提供实际商品、价格或自动比价结果。")}</Text>
    <Button className='secondary-button' disabled={busy || undefined} onClick={prepare}>{busy ? t("正在整理入口…") : t("生成站外搜索入口")}</Button>
    {error && <Text className='error-box'>{uiNotice(error)}</Text>}
    {notice && <Text className='notice-box'>{uiNotice(notice)}</Text>}
    {plan && <><Text className='field-help'>{locale === 'en' ? plan.sourceCoverageNote_en ?? plan.sourceCoverageNote : plan.sourceCoverageNote}</Text><View className='search-plan-items'>{plan.items.map((item, index) => {
      const query = queries[index] ?? item.query
      return <View className='search-plan-item' key={item.item_id ?? 'legacy-' + index}>
        <Text className='config-name'>{index + 1}. {item.name}</Text>
        <Text className='field-help'>{t("可精简搜索词，修改只影响本次跳转，不改变已确认需求。")}</Text>
        <Input className='search-query-input' value={query} maxlength={200} onInput={event => setQueries(previous => ({ ...previous, [index]: event.detail.value }))} />
        <Text className='search-query' selectable>{query}</Text>
        {(locale === 'en' ? item.query_notes_en ?? item.query_notes : item.query_notes)?.map((note, noteIndex) => <Text className='field-help' key={noteIndex}>{note}</Text>)}
        <Button className='secondary-button' disabled={!query.trim() || undefined} onClick={() => copy(query, t("关键词"))}>{t("复制关键词")}</Button>
        {item.sources.filter(source => market === 'all' || (market === 'CN' ? (source.market ?? 'CN') === 'CN' : source.market !== undefined && source.market !== 'CN')).map(source => {
          const target = targetFor(source, item, query)
          return <View className='search-platform' key={source.id}><Text className='config-name'>{label(source)}</Text>
            <Text className='field-help'>{locale === 'en' ? source.sourceCoverageNote_en ?? source.sourceCoverageNote : source.sourceCoverageNote}</Text>
            <View className='compact-actions'>
              <Button className='secondary-button external-search-button' disabled={!target || undefined} onClick={() => navigate(source, item, query)}>{t("去原平台继续搜索")}</Button>
              <Button className='secondary-button copy-search-link' disabled={!target || undefined} onClick={() => target && copy(target, t("搜索链接"))}>{t("复制链接")}</Button>
            </View>
            {target && <Text className='search-link' selectable>{target}</Text>}
          </View>
        })}
        <Text className='field-help'>{t("可能需要在原平台登录；没有返回结果不代表没有商品。这是搜索入口，不是商品详情“去原平台查看”。")}</Text>
      </View>
    })}</View></>}
  </View>
}
