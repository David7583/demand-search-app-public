import { t, useLocale } from '../i18n'
import { Button, Text, View } from '@tarojs/components'
import type { DemandVersion } from '../demand'

export const strategyLabels = { plan_first: '先给方案，再一起细化', explore_first: '先探索可行方向', execute_first: '按明确目标行动', verify_first: '先核实关键条件' }
type Props = { version: DemandVersion; selectedOption: string | null; editable: boolean; onSelect: (id: string) => void; onFeedback: (text: string) => void }
export default function SolutionWorkspace({ version, selectedOption, editable, onSelect, onFeedback }: Props) {
  useLocale()
  const plan = version.data.collaboration
  if (!plan) return <View className='solution-empty'><Text className='result-title'>{t("从具体方案开始讨论")}</Text><Text>{t("这个历史版本只有需求记录。继续对话后，初步方案、备选方向和行动步骤会在这里形成新版本。")}</Text></View>
  return <View className={'solution-workspace solution-' + plan.task_type}>
    <View className='solution-header'><Text className='solution-kicker'>{t(strategyLabels[plan.strategy])}</Text><Text className='solution-title'>{version.data.desired_outcome}</Text><Text className='field-help'>{plan.rationale}</Text><Text className='proposal-badge'>{version.data.solution_confirmed ? t("你已明确采纳方案 · 假设与估价仍待核实") : t("AI 临时方案 · 尚未采纳")}</Text></View>
    {plan.needs_verification && <View className='verification-note'>{t("存在关键条件待核实。下列内容用于讨论，不授权执行高风险或不可逆操作。")}</View>}
    {!!plan.assumptions.length && <View className='assumption-list'><Text className='result-title'>{t("先按这些假设讨论")}</Text>{plan.assumptions.map((text, i) => <Text key={i}>• {text}</Text>)}</View>}
    <View className='solution-options'>{plan.options.map(option => <View key={option.option_id} className={'solution-option' + (selectedOption === option.option_id ? ' option-selected' : '')}>
      <Text className='option-title'>{option.title}</Text><Text className='option-summary'>{option.summary}</Text>
      {option.budget_estimate && <View className='estimate'><Text>{t("暂估 ")}{option.budget_estimate.currency} {option.budget_estimate.low.toLocaleString()}–{option.budget_estimate.high.toLocaleString()}</Text><Text className='field-help'>{option.budget_estimate.basis} · {option.budget_estimate.note}{t(" · 不是商家报价，也不是已确认预算")}</Text></View>}
      {!!option.steps.length && <View className='solution-steps'>{option.steps.map((step, i) => <Text key={i}>{i + 1}. {step}</Text>)}</View>}
      {!!option.tradeoffs.length && <View className='tradeoffs'><Text className='field-help'>{t("差异与取舍")}</Text>{option.tradeoffs.map((text, i) => <Text key={i}>• {text}</Text>)}</View>}
      <View className='compact-actions'><Button className='secondary-button choose-option' disabled={!editable} onClick={() => onSelect(option.option_id)}>{selectedOption === option.option_id ? t("已选为待确认方案") : t("选择此方案待确认")}</Button><Button className='secondary-button' onClick={() => onFeedback(t("我想继续讨论版本 ") + version.number + t(" 的“") + option.title + '”：')}>{t("讨论这个方向")}</Button></View>
    </View>)}</View>
    {!!plan.next_steps.length && <View className='next-steps'><Text className='result-title'>{t("接下来可以做")}</Text>{plan.next_steps.map((text, i) => <Text key={i}>{i + 1}. {text}</Text>)}</View>}
    {!!plan.limitations.length && <View className='known-limits'><Text className='result-title'>{t("已知限制")}</Text>{plan.limitations.map((text, i) => <Text key={i}>• {text}</Text>)}</View>}
    {plan.task_type === 'shopping' && <Text className='field-help'>{t("当前仅整理需求和官方搜索入口，没有商品级数据，无法提供真实价格、供应商或匹配分数。")}</Text>}
    <Button className='secondary-button' onClick={() => onFeedback(t("针对版本 ") + version.number + t(" 的方案，我的反馈是："))}>{t("把反馈带回对话")}</Button>
  </View>
}
