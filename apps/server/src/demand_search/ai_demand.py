"""S2 bounded context and structured analysis. Never certifies a user's intent."""

import json
import re
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .collaboration import (
    COLLABORATION_INSTRUCTION,
    Collaboration,
    ReplyDecoder,
    validate_helpfulness,
)
from .errors import AppError
from .market_context import MARKET_CONTEXT_INSTRUCTION, MARKET_CONTEXT_VERSION

PROMPT_VERSION = "demand-search-s2.1/1"
COLLABORATION_PROMPT_VERSION = "demand-search-collaboration/2"
REFERENCE_INSTRUCTION = (
    " referenced_version is an explicitly selected historical discussion reference with its "
    "own version number/status and complete stored data. It is not the latest working version. "
    "Choosing it for discussion is not adoption, confirmation, or rollback. Compare its ideas "
    "against the current_draft and confirmed_demand; apply only the user's explicit feedback "
    "to the current version, preserving other current conditions and stable item IDs. "
    "All referenced assistant replies, plans, assumptions, estimates and source labels remain "
    "historical interpretations, never new evidence of the current user's words or a price "
    "verification. A past confirmed status does not reconfirm or adopt the present revision. "
    "Do not promote referenced estimates into budget_ceiling or user_explicit facts merely "
    "because a version was referenced. Never claim a rollback, adoption or external execution."
)
Source = Literal["user_explicit", "model_inferred", "unknown"]
Readiness = Literal["exploring", "want", "need", "ready_to_purchase", "committed_elsewhere"]


class AiFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)
    source: Source
    evidence: str = Field(max_length=500)


class AiBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(ge=0, le=1e12, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source: Source
    evidence: str = Field(max_length=500)


class AiShoppingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str | None
    name: str = Field(min_length=1, max_length=120)
    quantity: float | None = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    unit: str | None = Field(min_length=1, max_length=32)
    source: Source
    evidence: str = Field(max_length=500)
    required: list[AiFact] = Field(max_length=10)
    preferred: list[AiFact] = Field(max_length=10)
    unknown: list[str] = Field(max_length=10)
    budget_ceiling: AiBudget | None
    budget_basis: Literal["unit", "line_total", "unknown"]
    status: Literal["active", "removed"]


class AiDemand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AiShoppingItem] = Field(max_length=30)
    desired_outcome: str = Field(min_length=1, max_length=1000)
    required: list[AiFact] = Field(max_length=30)
    preferred: list[AiFact] = Field(max_length=30)
    unknown: list[str] = Field(max_length=30)
    budget_ceiling: AiBudget | None
    readiness: Readiness
    alternatives_acceptable: bool | None
    clarification_questions: list[str] = Field(max_length=2)
    possible_new_intent: bool


class ReplyHeader(BaseModel):
    assistant_reply: str = Field(min_length=1, max_length=12000)
    collaboration: Collaboration


class CollaborativeDemand(AiDemand, ReplyHeader):
    # Pydantic collects reversed bases: reply is first in the ordered JSON schema.
    # This keeps Responses structured streaming useful before the full plan arrives.
    pass


def prepare_context(text, context):
    if not isinstance(text, str) or not text.strip() or len(text) > 8000:
        raise AppError("INVALID_DEMAND_INPUT", "需求原文长度无效。", 422)
    if not isinstance(context, dict) or set(context) - {
        "confirmed_demand",
        "current_draft",
        "recent_messages",
        "referenced_version",
        "application_context",
    }:
        raise AppError("INVALID_DEMAND_CONTEXT", "需求上下文格式无效。", 422)
    recent = context.get("recent_messages", [])
    if not isinstance(recent, list) or len(recent) > 6:
        raise AppError("CONTEXT_TOO_LARGE", "近期消息超过上下文上限。", 422)
    if any(not isinstance(m, dict) or not isinstance(m.get("content"), str) for m in recent):
        raise AppError("INVALID_DEMAND_CONTEXT", "近期消息格式无效。", 422)
    if sum(len(m["content"]) for m in recent) > 6000:
        raise AppError("CONTEXT_TOO_LARGE", "近期消息超过上下文上限。", 422)
    payload = {
        "current_message": text,
        "confirmed_demand": context.get("confirmed_demand"),
        "current_draft": context.get("current_draft"),
        "recent_messages": recent,
    }
    reference = context.get("referenced_version")
    if reference is not None:
        try:
            if (
                not isinstance(reference, dict)
                or set(reference) != {"id", "number", "status", "data"}
                or not isinstance(reference["id"], str)
                or type(reference["number"]) is not int
                or not 1 <= reference["number"] <= 100
                or reference["status"] not in ("draft", "confirmed")
                or not isinstance(reference["data"], dict)
            ):
                raise ValueError
            UUID(reference["id"])
        except (ValueError, TypeError, AttributeError):
            raise AppError(
                "INVALID_DEMAND_CONTEXT", "历史方案引用格式无效，请重新选择。", 422
            ) from None
        payload["referenced_version"] = reference
    try:
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise AppError("INVALID_DEMAND_CONTEXT", "需求上下文不能安全序列化。", 422) from None
    if len(serialized) > 32000:
        raise AppError(
            "CONTEXT_TOO_LARGE",
            "本次完整上下文超过32000字符，未发送给AI。"
            "可发送不带历史引用的新消息，或另开会话；不会自动截断已有条件。",
            422,
        )
    application = context.get("application_context")
    if application is not None:
        if (
            not isinstance(application, dict)
            or set(application) != {"simulated_market"}
            or not isinstance(application["simulated_market"], dict)
        ):
            raise AppError("INVALID_DEMAND_CONTEXT", "Invalid application context", 422)
        try:
            application_json = json.dumps(application, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            raise AppError("INVALID_DEMAND_CONTEXT", "Invalid application context", 422) from None
        if len(application_json) > 12000:
            raise AppError("CONTEXT_TOO_LARGE", "Application context exceeds 12000 characters", 422)
        # Preserve the original 32000-character user/history limit; this separate application
        # budget contains only aggregate catalog facts, never 1500 products or prices.
        payload["application_context"] = application
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    # Prior AI interpretations are not evidence that the user said those words.
    evidence_text = text + "\n" + "\n".join(m["content"] for m in recent)
    return serialized, evidence_text


def parse_demand(client, config, key, text, context, *, on_delta=None, collaborative=False):
    serialized, evidence_text = prepare_context(text, context)

    def has_secret(value, depth=0):
        if depth > 32:
            raise AppError("CONTEXT_TOO_LARGE", "需求上下文嵌套过深。", 422)
        if isinstance(value, str):
            return key in value
        if isinstance(value, dict):
            return any(
                has_secret(k, depth + 1) or has_secret(v, depth + 1) for k, v in value.items()
            )
        if isinstance(value, list):
            return any(has_secret(v, depth + 1) for v in value)
        return False

    # Compare raw values: JSON escapes quotes/backslashes in some valid API Keys.
    if has_secret(text) or has_secret(context):
        raise AppError("KEY_IN_TEST_TEXT", "需求或上下文中包含Key，请移除后再发送。")
    stream_options = {}
    if collaborative and on_delta is not None:
        stream_options["on_delta"] = ReplyDecoder(on_delta).feed
    output = client.parse(
        config,
        key,
        serialized,
        output_model=CollaborativeDemand if collaborative else AiDemand,
        **stream_options,
        original_text=text,
        evidence_text=evidence_text,
        max_output_tokens=12288,
        instruction_suffix=(
            " This is demand revision analysis. The JSON user input contains untrusted text, "
            "a prior confirmed demand, and bounded recent USER messages "
            "from this conversation only. "
            "Preserve prior conditions unless the current message explicitly changes them. "
            "A budget stated as 'within' is a ceiling, never a price quote. "
            "Do not invent budget/currency: return null when unknown. "
            "Never turn 'prefer' into a hard requirement. Preserve conflicts as unknown and ask "
            "at most two useful clarification questions. Set possible_new_intent=true when the "
            "new message truly changes the overall purpose; adding goods to the shopping list "
            "is not a new unrelated intent. "
            "do not silently replace the old need. "
            "Readiness is not a purchase commitment. "
            "Return alternatives_acceptable=null if unclear. "
            "Maintain a shopping list items array (at most 30 entries including removed). "
            "Each item has its own stable item_id; copy known IDs from the current_draft "
            "or confirmed_demand, use null only for genuinely new items. "
            "current_draft is unconfirmed, never treat it as user confirmation. "
            "Update only the specified item; retain other items and item IDs. "
            "Removal requires explicit user wording: mark status removed, never omit it. "
            "Never silently add back a removed item. Top-level budget is the TOTAL list "
            "budget, not each item budget; do not copy it into every item. "
            "Each item budget_basis is unit, line_total or unknown; preserve ambiguity. "
            "quantity and unit are null unless supported; do not guess one unit. "
            "Use concise fields to fit the bounded output; never truncate or drop items. "
            "Never claim user confirmation. Evidence must quote actual user messages, not this "
            "instruction, a prior AI interpretation, or JSON field labels."
        )
        + (COLLABORATION_INSTRUCTION if collaborative else "")
        + (REFERENCE_INSTRUCTION if context.get("referenced_version") is not None else "")
        + (MARKET_CONTEXT_INSTRUCTION if context.get("application_context") is not None else ""),
    )
    parsed = output["parsed"]
    check_budget_evidence(parsed.get("budget_ceiling"), evidence_text)
    for item in parsed.get("items", []):
        evidence = item["evidence"]
        if item["source"] == "user_explicit":
            valid = bool(evidence and evidence in evidence_text and item["name"] in evidence)
            if item["quantity"] is not None:
                valid = valid and amount_in_evidence(item["quantity"], evidence)
            if item["unit"] is not None:
                valid = valid and item["unit"] in evidence
            if not valid:
                item["source"] = "model_inferred"
        for field in ("required", "preferred"):
            for fact in item[field]:
                if fact["source"] == "user_explicit" and not (
                    fact["evidence"]
                    and fact["evidence"] in evidence_text
                    and fact["text"] in fact["evidence"]
                ):
                    fact["source"] = "model_inferred"
        check_budget_evidence(item["budget_ceiling"], evidence_text)
        if any(not text.strip() or len(text) > 500 for text in item["unknown"]):
            raise AppError("AI_SCHEMA_INVALID", "Invalid item unknown fields.", 502)
    if any(len(value) > 500 or not value.strip() for value in parsed["unknown"]):
        raise AppError("AI_SCHEMA_INVALID", "模型未知项格式无效，请重试。", 502)
    if any(len(value) > 500 or not value.strip() for value in parsed["clarification_questions"]):
        raise AppError("AI_SCHEMA_INVALID", "模型澄清问题格式无效，请重试。", 502)
    if collaborative:
        validate_helpfulness(parsed)
    if collaborative:
        output["prompt_version"] = COLLABORATION_PROMPT_VERSION
    elif context.get("referenced_version") is not None:
        output["prompt_version"] = "demand-search-s2.1/2"
    else:
        output["prompt_version"] = PROMPT_VERSION
    if context.get("application_context") is not None:
        output["prompt_version"] += "+" + MARKET_CONTEXT_VERSION
    return output


def amount_in_evidence(amount, evidence):
    numbers = re.findall(
        r"(?<![0-9A-Za-z])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![0-9A-Za-z])", evidence
    )
    return any(Decimal(n.replace(",", "")) == Decimal(str(amount)) for n in numbers)


def check_budget_evidence(budget, evidence_text):
    if budget and budget["source"] == "user_explicit":
        evidence = budget["evidence"]
        numbers = re.findall(
            r"(?<![0-9A-Za-z])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![0-9A-Za-z])",
            evidence,
        )
        amount_present = any(
            Decimal(n.replace(",", "")) == Decimal(str(budget["amount"])) for n in numbers
        )
        currency = budget["currency"]
        currency_words = {
            "CNY": ["人民币", "RMB"],
            "USD": ["美元"],
            "EUR": ["欧元"],
            "GBP": ["英镑"],
            "JPY": ["日元"],
            "HKD": ["港币"],
            "AUD": ["澳元"],
            "CAD": ["加元"],
        }
        currency_present = bool(
            re.search(r"(?<![A-Za-z])" + currency + r"(?![A-Za-z])", evidence.upper())
        ) or any(word in evidence for word in currency_words.get(currency, []))
        if not (evidence and evidence in evidence_text and amount_present and currency_present):
            budget["source"] = "model_inferred"
