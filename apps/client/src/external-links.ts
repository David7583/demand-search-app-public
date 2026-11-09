export type SearchSource = {
  id: string; label: string; status: string; homepage_url: string
  search_url: string | null; link_kind: 'platform_home' | 'keyword_search'; verification_note: string
  sourceCoverageNote?: string; sourceCoverageNote_en?: string; label_en?: string; market?: 'CN' | 'US' | 'GLOBAL'; verification_note_en?: string
}
const homes: Record<string, string[]> = {
  amazon_us: ['https://www.amazon.com/'], ebay_us: ['https://www.ebay.com/'],
  walmart_us: ['https://www.walmart.com/'], etsy: ['https://www.etsy.com/'],
  taobao: ['https://www.taobao.com/'], jd: ['https://www.jd.com/'],
  pinduoduo: ['https://www.pinduoduo.com/', 'https://mobile.yangkeduo.com/'],
}
const searches: Record<string, string> = {
  amazon_us: 'https://www.amazon.com/s?k=', ebay_us: 'https://www.ebay.com/sch/i.html?_nkw=',
  walmart_us: 'https://www.walmart.com/search?q=', etsy: 'https://www.etsy.com/search?q=',
  taobao: 'https://s.taobao.com/search?q=',
  jd: 'https://search.jd.com/Search?keyword=',
  pinduoduo: 'https://mobile.yangkeduo.com/search_result.html?search_key=',
}
// Pure, fixed-template construction also works without browser URL/WebCrypto APIs.
export function buildFallbackSearchLink(providerId: string, query: string): string | null {
  if (!Object.hasOwn(searches, providerId) || typeof query !== 'string' || !query.trim() ||
      query.length > 200 || /[\u0000-\u001f\u007f]/.test(query)) return null
  try {
    return searches[providerId] + encodeURIComponent(query).replace(/[!'()*]/g, char => '%' + char.charCodeAt(0).toString(16).toUpperCase())
  } catch { return null }
}
export function externalSearchTarget(source: SearchSource, query: string): string | null {
  if (typeof query !== 'string' || !Object.hasOwn(homes, source.id) || !query.trim() || query.length > 200 || !homes[source.id]?.includes(source.homepage_url)) return null
  if (source.link_kind === 'platform_home' && source.search_url === null) return source.homepage_url
  const target = buildFallbackSearchLink(source.id, query)
  return source.link_kind === 'keyword_search' && target !== null && source.search_url === target ? target : null
}
