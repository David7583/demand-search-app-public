"""Local external-search plans. No product API, scraping, prices or network calls."""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from urllib.parse import quote, urlencode

from .config import Settings
from .errors import AppError
from .history_service import HistoryService, checked_id, checked_text
from .storage import LOCAL_OWNER, connect

MAX_ITEMS = 30
MAX_QUERY = 200
_ALLOWED_HOMES = {
    "taobao": "https://www.taobao.com/",
    "jd": "https://www.jd.com/",
    "pinduoduo": "https://mobile.yangkeduo.com/",
    "amazon_us": "https://www.amazon.com/",
    "ebay_us": "https://www.ebay.com/",
    "walmart_us": "https://www.walmart.com/",
    "etsy": "https://www.etsy.com/",
}

_ALLOWED_SEARCHES = {
    "taobao": ("https://s.taobao.com/search", "q"),
    "jd": ("https://search.jd.com/Search", "keyword"),
    "pinduoduo": ("https://mobile.yangkeduo.com/search_result.html", "search_key"),
    "amazon_us": ("https://www.amazon.com/s", "k"),
    "ebay_us": ("https://www.ebay.com/sch/i.html", "_nkw"),
    "walmart_us": ("https://www.walmart.com/search", "q"),
    "etsy": ("https://www.etsy.com/search", "q"),
}
COVERAGE_NOTE = (
    "本版本不接商品或联盟 API；仅生成原平台关键词搜索链接，没有读取商品、价格、库存或完成自动比较。"
)

COVERAGE_NOTE_EN = (
    "Official keyword search links only. No product or affiliate API is connected; "
    "no products, prices or inventory have been retrieved or automatically compared."
)


@dataclass(frozen=True)
class ProductSourceEntry:
    """A source entry is not evidence of an authorized product-search connection."""

    id: Literal["taobao", "jd", "pinduoduo", "amazon_us", "ebay_us", "walmart_us", "etsy"]
    label: str
    homepage_url: str
    label_en: str = ""
    market: Literal["CN", "US", "GLOBAL"] = "CN"

    def plan_entry(self, query):
        if self.homepage_url != _ALLOWED_HOMES.get(self.id):
            raise AppError("EXTERNAL_LINK_INVALID", "平台入口不在允许列表中。", 500)
        base, parameter = _ALLOWED_SEARCHES[self.id]
        keyword_url = base + "?" + urlencode({parameter: search_query(query)}, quote_via=quote)
        return {
            "id": self.id,
            "label": self.label,
            "label_en": self.label_en or self.label,
            "market": self.market,
            "status": "not_configured",
            "homepage_url": self.homepage_url,
            "search_url": keyword_url,
            "link_kind": "keyword_search",
            "sourceCoverageNote": COVERAGE_NOTE,
            "sourceCoverageNote_en": COVERAGE_NOTE_EN,
            "verification_note": (
                "中国平台：2026-11-04 曾匿名打开合成关键词地址，京东转到登录页；"
                "海外平台：2026-11-05 仅核对固定官方搜索模板，目标站点可能要求登录、"
                "JavaScript 或人机验证，不能保证当前网络可达或有符合条件的商品。"
                "关键词不等于精确过滤；不自动翻译、换汇或确认配送地区。"
            ),
            "verification_note_en": (
                "Official search URL templates only; destination access and matching products are "
                "not guaranteed. Sites may require login, JavaScript or human verification. "
                "Keywords do not enforce filters. No automatic translation, currency conversion "
                "or shipping-region verification."
            ),
        }


SOURCES = (
    ProductSourceEntry("taobao", "淘宝", "https://www.taobao.com/", "Taobao"),
    ProductSourceEntry("jd", "京东", "https://www.jd.com/", "JD.com"),
    ProductSourceEntry("pinduoduo", "拼多多", "https://mobile.yangkeduo.com/", "Pinduoduo"),
    ProductSourceEntry("amazon_us", "Amazon 美国", "https://www.amazon.com/", "Amazon US", "US"),
    ProductSourceEntry("ebay_us", "eBay 美国", "https://www.ebay.com/", "eBay US", "US"),
    ProductSourceEntry(
        "walmart_us", "Walmart 美国", "https://www.walmart.com/", "Walmart US", "US"
    ),
    ProductSourceEntry("etsy", "Etsy", "https://www.etsy.com/", "Etsy", "GLOBAL"),
)


def search_query(name):
    checked_text(name, label="search term", limit=10000)
    # Match the client JS string length; never silently discard requested terms.
    if len(name.encode("utf-16-le")) // 2 > MAX_QUERY:
        raise AppError(
            "SEARCH_QUERY_TOO_LONG",
            "名称和已确认条件合并后超过200字，请精简项目名称或硬约束后确认新版本。",
            422,
        )
    query = re.sub(r"\s+", " ", name).strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in query):
        raise AppError("SEARCH_QUERY_INVALID", "搜索词包含不可用的控制字符。", 422)
    return query


def item_plan(item, common_required):
    if item.get("confirmed") is not True or item.get("source") == "unknown":
        raise AppError("SEARCH_ITEM_UNCONFIRMED", "请先确认每个待搜索项目的名称。", 409)
    parts = [item["name"]]
    included_required = []
    for fact in [*common_required, *item.get("required", [])]:
        if fact.get("confirmed") is True and fact.get("source") != "unknown":
            term = fact["text"]
            if term not in parts:
                parts.append(term)
                included_required.append(term)
    notes = []
    notes_en = []
    budget = item.get("budget_ceiling")
    basis = item.get("budget_basis", "unknown")
    if budget:
        if budget.get("confirmed") is not True or budget.get("source") == "unknown":
            notes.append("未确认的单项预算未加入搜索词。")
            notes_en.append("Unconfirmed item budgets are excluded from the search terms.")
        elif basis not in {"unit", "line_total"}:
            notes.append("预算是单价还是该项合计尚未明确，未加入搜索词。")
            notes_en.append("Budget excluded: its per-unit or line-total basis is not specified.")
        else:
            amount = format(Decimal(str(budget["amount"])), "f")
            if "." in amount:
                amount = amount.rstrip("0").rstrip(".")
            label = "单价上限" if basis == "unit" else "该项合计预算上限"
            parts.append(label + amount + " " + budget["currency"])
            notes.append("预算只作为关键词，不代表平台已经按价格过滤。")
            notes_en.append("Budgets are plain keywords, not verified price filters.")
    query = search_query(" ".join(parts))
    return {
        "item_id": item["item_id"],
        "name": item["name"],
        "query": query,
        "included_required": included_required,
        "query_notes": notes,
        "query_notes_en": notes_en,
        "sources": [source.plan_entry(query) for source in SOURCES],
    }


class ProductSearchPlanService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.history = HistoryService(settings)

    def plan(self, conversation_id, version_id, item_ids=None):
        conversation_id, version_id = checked_id(conversation_id), checked_id(version_id)
        if item_ids is not None:
            if not isinstance(item_ids, list) or not 1 <= len(item_ids) <= MAX_ITEMS:
                raise AppError("SEARCH_ITEMS_INVALID", "请选择 1 到 30 个清单项目。", 422)
            item_ids = [checked_id(value) for value in item_ids]
            if len(set(item_ids)) != len(item_ids):
                raise AppError("SEARCH_ITEMS_INVALID", "不能重复选择同一个清单项目。", 422)
        with connect(self.settings) as db:
            self.history._conversation(db, conversation_id)
            row = db.execute(
                "SELECT v.id,v.number,v.status,v.created_at,v.data_json,"
                "d.status AS demand_status,d.confirmed_version_id,d.current_version_id "
                "FROM demand_versions v JOIN demands d ON v.demand_id=d.id "
                "WHERE d.conversation_id=? AND d.owner_id=? AND v.id=?",
                (conversation_id, LOCAL_OWNER, version_id),
            ).fetchone()
            if row is None:
                raise AppError("DEMAND_VERSION_NOT_FOUND", "本会话不存在该需求版本。", 404)
            if row["demand_status"] == "withdrawn":
                raise AppError("DEMAND_WITHDRAWN", "已撤回的需求不能生成新的搜索计划。", 409)
            if row["status"] != "confirmed":
                raise AppError("DEMAND_CONFIRMATION_REQUIRED", "请先检查并确认清单版本。", 409)
            data = json.loads(row["data_json"])
        items = data.get("items", [])
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise AppError("SEARCH_ITEMS_INVALID", "清单项目数量或结构无效。", 422)
        if items:
            active = [item for item in items if item.get("status") == "active"]
            active_ids = {item["item_id"] for item in active}
            if item_ids is not None and not set(item_ids).issubset(active_ids):
                raise AppError("SEARCH_ITEM_NOT_FOUND", "所选项目不属于该版本或已被移除。", 404)
            selected = [item for item in active if item_ids is None or item["item_id"] in item_ids]
        elif item_ids is not None:
            raise AppError("SEARCH_ITEM_NOT_FOUND", "此历史需求没有独立清单项目。", 404)
        else:
            # Original S2 snapshots are read without rewriting data or creating items.
            selected = [
                {
                    "item_id": None,
                    "name": data["desired_outcome"],
                    "source": "user_confirmed",
                    "confirmed": True,
                    "budget_ceiling": data.get("budget_ceiling"),
                    "budget_basis": "line_total",
                }
            ]
        if not selected:
            raise AppError("SEARCH_ITEMS_EMPTY", "清单中没有可搜索的项目。", 409)
        return {
            "kind": "external_search_plan",
            "version_id": row["id"],
            "version_number": row["number"],
            "version_created_at": row["created_at"],
            "is_latest_confirmed": row["id"] == row["confirmed_version_id"],
            "is_current_version": row["id"] == row["current_version_id"],
            "network_searched": False,
            "offers": [],
            "sourceCoverageNote": COVERAGE_NOTE,
            "sourceCoverageNote_en": COVERAGE_NOTE_EN,
            "limitations_en": [
                COVERAGE_NOTE_EN,
                "Keywords are prepared locally; you decide whether to copy or send them.",
                "No product results have been retrieved. This is not cross-platform comparison.",
                "Platform login, region, app and verification requirements are not bypassed.",
            ],
            "items": [item_plan(item, data.get("required", [])) for item in selected],
            "limitations": [
                COVERAGE_NOTE,
                "仅在本机整理关键词；打开平台、复制或提交搜索词由用户另行决定。",
                "未检索商品，不表示任何平台没有商品，也不表示已完成跨平台自动比较。",
                "平台内登录、验证码、地区与 App 限制由平台决定，本应用不会绕过。",
            ],
        }
