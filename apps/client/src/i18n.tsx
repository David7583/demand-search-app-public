import { useSyncExternalStore } from 'react'
import { Button, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { localeStorageKey, normalizeLocale, translate, translateNotice } from './i18n-core'
import type { Locale } from './i18n-core'
const listeners = new Set<() => void>()
let locale: Locale = 'zh-CN'
try { if (typeof window !== 'undefined') locale = normalizeLocale(window.localStorage.getItem(localeStorageKey)) } catch { /* Private-mode storage may be unavailable. */ }
function updateDocument() {
  if (typeof document === 'undefined') return
  document.documentElement.lang = locale
  document.title = locale === 'en' ? 'Demand Search App' : '需求端平台 · Demand Search App'
}
updateDocument()
// Taro loads the static navigation title after page onShow and before onReady.
// Synchronize through its public API after readiness so the router cache also
// preserves the chosen language when the page is shown again.
export function syncPageLocale() {
  updateDocument()
  if (process.env.TARO_ENV !== 'h5' || typeof document === 'undefined') return
  void Taro.setNavigationBarTitle({ title: document.title }).catch(() => { updateDocument() })
}
export function getLocale(): Locale { return locale }
export function setLocale(value: Locale) {
  locale = normalizeLocale(value)
  try { if (typeof window !== 'undefined') window.localStorage.setItem(localeStorageKey, locale) } catch { /* In-memory switching remains available. */ }
  syncPageLocale()
  listeners.forEach(listener => listener())
}
export function useLocale(): Locale {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener) } }, getLocale, () => 'zh-CN')
}
export function t(source: string): string { return translate(source, locale) }
export function uiNotice(message: string): string { return translateNotice(message, locale) }
export function LanguageSwitch() {
  useLocale()
  return <View className='language-switch' role='group' aria-label={t('界面语言')}>
    <Button className={locale === 'zh-CN' ? 'language-active' : ''} onClick={() => setLocale('zh-CN')} aria-pressed={locale === 'zh-CN'}>中文</Button>
    <Button className={locale === 'en' ? 'language-active' : ''} onClick={() => setLocale('en')} aria-pressed={locale === 'en'}>English</Button>
  </View>
}
