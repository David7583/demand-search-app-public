import { t, useLocale } from '../i18n'
import Textarea from './AppTextarea'
import { Button, Input, Label, Text, View } from '@tarojs/components'
import { useState } from 'react'
import { sourceLabels } from '../demand'
import type { DemandItem } from '../demand'

export type ItemEditor = { item_id: string; name: string; quantity: string; unit: string; required: string; preferred: string; unknown: string; budget: string; currency: string; budget_basis: 'unit' | 'line_total' | 'unknown'; status: 'active' | 'removed' }
const lines = (value: string) => value.split('\n').map(line => line.trim()).filter(Boolean)
export function itemEditor(item: DemandItem): ItemEditor {
  return { item_id: item.item_id, name: item.name, quantity: item.quantity === null ? '' : String(item.quantity), unit: item.unit ?? '',
    required: item.required.map(fact => fact.text).join('\n'), preferred: item.preferred.map(fact => fact.text).join('\n'), unknown: item.unknown.join('\n'),
    budget: item.budget_ceiling === null ? '' : String(item.budget_ceiling.amount), currency: item.budget_ceiling?.currency ?? 'CNY', budget_basis: item.budget_basis, status: item.status }
}
export function itemEdits(items: ItemEditor[]) {
  return items.map(item => {
    const quantity = item.quantity.trim() ? Number(item.quantity) : null
    const amount = item.budget.trim() ? Number(item.budget) : null
    if (!item.name.trim() || item.name.trim().length > 120 || (quantity !== null && (!Number.isFinite(quantity) || quantity <= 0 || quantity > 1e6)) ||
      (amount !== null && (!Number.isFinite(amount) || amount < 0 || amount > 1e12 || !/^[A-Z]{3}$/.test(item.currency)))) throw new Error(t("请检查每项名称、正数数量和预算；留空表示未知。"))
    return { item_id: item.item_id, name: item.name.trim(), quantity, unit: item.unit.trim() || null,
      required: lines(item.required), preferred: lines(item.preferred), unknown: lines(item.unknown),
      budget_ceiling: amount === null ? null : { amount, currency: item.currency }, budget_basis: item.budget_basis, status: item.status }
  })
}
type Props = { items: ItemEditor[]; original: DemandItem[]; editable: boolean; onChange: (items: ItemEditor[]) => void }
export default function ShoppingListEditor({ items, original, editable, onChange }: Props) {
  useLocale()
  const [expanded, setExpanded] = useState<string | null>(null)
  function update(id: string, patch: Partial<ItemEditor>) {
    if (editable) onChange(items.map(item => item.item_id === id ? { ...item, ...patch } : item))
  }
  return <View className='shopping-list-editor'>
    <View className='demand-heading'><Text className='result-title'>{t("需求清单 · ")}{items.filter(item => item.status === 'active').length}{t(" 项")}</Text></View>
    <Text className='field-help'>{t("可在对话中一次描述多件物品，再补充、修改或移除。每项预算与整份清单总预算分开；数量、条件或预算未知时保留未知。")}</Text>
    {!items.length && <Text className='field-help'>{t("当前版本还没有拆分清单，可继续对话补充物品；原有需求不会丢失。")}</Text>}
    {items.map((item, index) => {
      const evidence = original.find(value => value.item_id === item.item_id)
      const dirty = !evidence || JSON.stringify(item) !== JSON.stringify(itemEditor(evidence))
      const open = expanded === item.item_id
      return <View key={item.item_id} className={'shopping-item' + (item.status === 'removed' ? ' item-removed' : '')} data-item-id={item.item_id}>
        <View className='shopping-item-summary'>
          <View className='shopping-item-copy'><Text className='item-name'>{index + 1}. {item.name || t("待填写名称")}{item.status === 'removed' ? t(" · 已移除") : ''}</Text>
            <Text className='field-help'>{item.quantity ? item.quantity + (item.unit || t("（单位未知）")) : t("数量未知")} · {item.budget ? item.currency + ' ' + item.budget + (item.budget_basis === 'unit' ? t("/件") : item.budget_basis === 'line_total' ? t("（本项合计上限）") : t("（预算口径待确认）")) : t("本项预算未知")}</Text>
            <Text className='source-label'>{dirty ? t("本次修改尚未确认 · 原记录：") : ''}{evidence ? t(sourceLabels[evidence.source]) + (evidence.confirmed ? t(" · 已确认") : t(" · 待确认")) : t("用户新增 · 待确认")}</Text>
          </View>
          <Button className='secondary-button item-expand' onClick={() => setExpanded(open ? null : item.item_id)}>{open ? t("收起") : editable ? t("查看 / 修改") : t("查看详情")}</Button>
        </View>
        {open && <View className='shopping-item-details'>
          <View className='field'><Label>{t("物品或服务名称")}</Label><Input className='item-name-input' value={item.name} maxlength={120} disabled={!editable} onInput={event => update(item.item_id, { name: event.detail.value })} /></View>
          <View className='demand-columns'><View className='field'><Label>{t("数量（可留空）")}</Label><Input className='item-quantity' type='digit' value={item.quantity} disabled={!editable} onInput={event => update(item.item_id, { quantity: event.detail.value })} /></View><View className='field'><Label>{t("单位（可留空）")}</Label><Input className='item-unit' value={item.unit} maxlength={32} disabled={!editable} onInput={event => update(item.item_id, { unit: event.detail.value })} /></View></View>
          <View className='demand-columns'><View className='field'><Label>{t("本项预算上限（可留空）")}</Label><Input className='item-budget' type='digit' value={item.budget} disabled={!editable} onInput={event => update(item.item_id, { budget: event.detail.value })} /></View><View className='field'><Label>{t("货币代码")}</Label><Input className='item-currency' value={item.currency} maxlength={3} disabled={!editable} onInput={event => update(item.item_id, { currency: event.detail.value.toUpperCase() })} /></View></View>
          <View className='inline-actions'>{([{ value: 'unit', label: t("每件上限") }, { value: 'line_total', label: t("本项合计上限") }, { value: 'unknown', label: t("口径未知") }] as const).map(option => <Button key={option.value} className={'secondary-button budget-basis' + (item.budget_basis === option.value ? ' selected' : '')} disabled={!editable} onClick={() => update(item.item_id, { budget_basis: option.value })}>{option.label}</Button>)}</View>
          {([{ field: 'required', label: t("必须满足") }, { field: 'preferred', label: t("偏好") }, { field: 'unknown', label: t("仍然未知") }] as const).map(field => <View className='field' key={field.field}><Label>{field.label}{t("（每行一项）")}</Label><Textarea className={'demand-field item-' + field.field} value={item[field.field]} maxlength={5000} disabled={!editable} onInput={event => update(item.item_id, { [field.field]: event.detail.value })} /></View>)}
          {evidence?.evidence && <Text className='field-help'>{t("名称与数量依据：")}{evidence.evidence}</Text>}
          {evidence && [...evidence.required, ...evidence.preferred].map((fact, factIndex) => <Text className='field-help' key={factIndex}>{fact.text} · {t(sourceLabels[fact.source])}{fact.confirmed ? t(" · 已确认") : t(" · 待确认")}</Text>)}
          {evidence?.budget_ceiling && <Text className='field-help'>{t("原版本预算来源：")}{t(sourceLabels[evidence.budget_ceiling.source])}{evidence.budget_ceiling.confirmed ? t(" · 已确认") : t(" · 待确认")}</Text>}
          {editable && <Button className='secondary-button item-remove' onClick={() => update(item.item_id, { status: item.status === 'active' ? 'removed' : 'active' })}>{item.status === 'active' ? t("从清单移除此项") : t("恢复此项")}</Button>}
        </View>}
      </View>
    })}
    {items.length >= 30 && <Text className='field-help'>{t("当前实验版每份清单最多保留30项（含已移除项），可继续修改现有项。")}</Text>}
  </View>
}
