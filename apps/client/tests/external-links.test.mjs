import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildFallbackSearchLink, externalSearchTarget } from '../src/external-links.ts'
const source = { id: 'jd', label: '京东', status: 'not_configured', homepage_url: 'https://www.jd.com/', search_url: null, link_kind: 'platform_home', verification_note: '' }
test('external links bind to exact official source and user-visible keyword', () => {
  assert.equal(externalSearchTarget(source, '办公椅'), source.homepage_url)
  const keyword = { ...source, link_kind: 'keyword_search', search_url: 'https://search.jd.com/Search?keyword=' + encodeURIComponent('办公椅') }
  assert.ok(externalSearchTarget(keyword, '办公椅'))
  assert.equal(externalSearchTarget(keyword, '私人上下文'), null)
  for (const link of ['javascript:alert(1)', 'https://search.jd.com.evil.example/Search?keyword=x', 'https://user@search.jd.com/Search?keyword=x', 'https://search.jd.com/Search?keyword=x&redirect=https://evil.example', 'https://search.jd.com/Search?keyword=x&keyword=x']) {
    assert.equal(externalSearchTarget({ ...keyword, search_url: link }, 'x'), null)
  }
  assert.equal(externalSearchTarget({ ...source, homepage_url: 'https://evil.example/' }, 'x'), null)
  assert.equal(externalSearchTarget({ ...source, id: '__proto__' }, 'x'), null)
  assert.equal(externalSearchTarget(source, ' '), null)
  assert.equal(externalSearchTarget(source, 'x'.repeat(201)), null)
})

test('fallback keyword URLs encode arbitrary text without acquiring data or accepting custom hosts', () => {
  const query = "chair & price=1?#'()*!"
  for (const [id, host, key] of [
    ['taobao', 's.taobao.com', 'q'], ['jd', 'search.jd.com', 'keyword'],
    ['pinduoduo', 'mobile.yangkeduo.com', 'search_key'],
    ['amazon_us', 'www.amazon.com', 'k'], ['ebay_us', 'www.ebay.com', '_nkw'],
    ['walmart_us', 'www.walmart.com', 'q'], ['etsy', 'www.etsy.com', 'q'],
  ]) {
    const url = new URL(buildFallbackSearchLink(id, query))
    assert.equal(url.hostname, host)
    assert.equal(url.searchParams.get(key), query)
    assert.deepEqual([...url.searchParams.keys()], [key])
    assert.equal(url.hash, '')
  }
  for (const id of ['__proto__', 'constructor', 'https://evil.example']) assert.equal(buildFallbackSearchLink(id, query), null)
  for (const text of ['', ' '.repeat(5), 'x'.repeat(201), '\u0000', '\ud800']) assert.equal(buildFallbackSearchLink('jd', text), null)
})

test('international links reject substituted hosts and keep user keywords verbatim', () => {
  for (const [id, home] of [['amazon_us', 'https://www.amazon.com/'], ['ebay_us', 'https://www.ebay.com/'], ['walmart_us', 'https://www.walmart.com/'], ['etsy', 'https://www.etsy.com/']]) {
    const query = '办公椅 chair CNY 1500 & USD?';
    const entry = { id, label: id, status: 'not_configured', homepage_url: home, search_url: buildFallbackSearchLink(id, query), link_kind: 'keyword_search', verification_note: '' }
    assert.equal(externalSearchTarget(entry, query), entry.search_url)
    assert.equal(externalSearchTarget({ ...entry, homepage_url: home.replace('.com', '.com.evil.example') }, query), null)
    assert.equal(externalSearchTarget({ ...entry, search_url: entry.search_url + '&tracking=untrusted' }, query), null)
    assert.equal(externalSearchTarget(entry, 'translated keyword'), null)
  }
})
