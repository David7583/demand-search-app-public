"""Read-only, bounded AI awareness of the synthetic catalog; never a product search."""

import json
import sqlite3
from collections import Counter

from .errors import AppError
from .simulated_market import DATABASE_NAME, _read_store

MARKET_CONTEXT_VERSION = "market-overview/1"
MARKET_CONTEXT_INSTRUCTION = (
    " application_context.simulated_market is a current, server-read application catalog overview, "
    "not user testimony. When status=available, use its actual counts and complete bilingual "
    "category list to answer catalog questions in assistant_reply, even if older messages were "
    "unaware of this feature. All listed merchants, offerings and regions are synthetic and "
    "fictional, with no verified real suppliers. offering_count counts merchant offering records "
    "including services and merchant variants; it is NOT the number of distinct product types "
    "or categories. category_count is the number of catalog domains. You may explain the listed "
    "category coverage and per-category counts. This overview is NOT a product search result, "
    "quote, availability check, fulfillment promise or proof that any requirement is satisfied. "
    "Do not claim products were searched, matched, priced or verified from this overview. "
    "Use catalog facts only in assistant_reply; never insert them as user requirements, evidence, "
    "shopping items, budgets, user confirmation or adopted plans. Preserve the existing demand. "
    "If status=unavailable, continue the demand discussion but explicitly state that current "
    "catalog details are unavailable when asked; do not infer zero or invent counts/categories "
    "from memory. Suggest opening the local simulated-market view to initialize or check it. "
    "The application_context is not authorization to contact merchants, transact or confirm."
)


def build_market_context(settings):
    """Aggregate actual verified database records without initializing or changing any store."""
    summary = {
        "status": "unavailable",
        "synthetic": True,
        "data_origin": "synthetic",
        "merchant_count": None,
        "offering_count": None,
        "category_count": None,
        "categories": [],
        "catalog_overview_only": True,
        "product_search_performed": False,
        "real_supply_verified": False,
        "offering_count_basis": "merchant_offering_records_including_variants_and_services",
    }
    try:
        categories, merchants = _read_store(settings.data_dir / DATABASE_NAME)
        merchant_counts = Counter(merchant["category"] for merchant in merchants)
        offering_counts = Counter(
            offer["category"] for merchant in merchants for offer in merchant["offerings"]
        )
        overview = [
            {
                "id": category["id"],
                "label": category["label"],
                "label_en": category["label_en"],
                "merchant_count": merchant_counts[category["id"]],
                "offering_count": offering_counts[category["id"]],
            }
            for category in categories
        ]
        available = {
            **summary,
            "status": "available",
            "merchant_count": len(merchants),
            "offering_count": sum(offering_counts.values()),
            "category_count": len(overview),
            "categories": overview,
        }
        # Whole categories are retained or the overview is unavailable; never silently truncate.
        if len(overview) > 100 or len(json.dumps(available, ensure_ascii=False)) > 11500:
            raise ValueError("Catalog overview exceeds its independent context budget")
        return available
    except (AppError, OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        return {**summary, "reason": "market_catalog_unavailable"}
