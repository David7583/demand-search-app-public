"""Application-owned provisional plans and incremental reply decoding."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import AppError

Short = Annotated[str, Field(min_length=1, max_length=600)]
Steps = Annotated[list[Short], Field(max_length=12)]


class Bounded(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Estimate(Bounded):
    low: float = Field(ge=0, le=1e12)
    high: float = Field(ge=0, le=1e12)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    basis: Short
    note: Short

    @model_validator(mode="after")
    def ordered(self):
        if self.high < self.low:
            raise ValueError("Estimate range reversed")
        return self


class Option(Bounded):
    option_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1600)
    steps: Steps
    tradeoffs: Annotated[list[Short], Field(max_length=8)]
    budget_estimate: Estimate | None


class Collaboration(Bounded):
    strategy: Literal["plan_first", "explore_first", "execute_first", "verify_first"]
    rationale: Short
    task_type: Literal["planning", "exploration", "shopping", "general"]
    assumptions: Annotated[list[Short], Field(max_length=12)]
    options: Annotated[list[Option], Field(max_length=5)]
    next_steps: Steps
    limitations: Annotated[list[Short], Field(min_length=1, max_length=12)]
    needs_verification: bool

    @model_validator(mode="after")
    def consistency(self):
        def nonblank(value):
            if isinstance(value, str):
                if not value.strip() or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                    raise ValueError("Blank or invalid plan text")
            elif isinstance(value, dict):
                for part in value.values():
                    nonblank(part)
            elif isinstance(value, list):
                for part in value:
                    nonblank(part)

        nonblank(self.model_dump())
        identities = [option.option_id for option in self.options]
        if len(identities) != len(set(identities)):
            raise ValueError("Repeated option ID")
        if self.needs_verification != (self.strategy == "verify_first"):
            raise ValueError("Critical verification overrides action")
        if self.strategy == "plan_first" and not self.options:
            raise ValueError("A plan-first response must supply a discussable option")
        if self.strategy == "explore_first" and len(self.options) < 2:
            raise ValueError("Exploration must offer candidate directions, not only questions")
        if self.strategy == "execute_first" and not self.next_steps:
            raise ValueError("Execution must supply useful actionable work")
        return self


class Selection(Bounded):
    option_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    status: Literal["user_selected"]


def validate_helpfulness(data):
    """Enforce shape/decision consistency, never claim to certify model correctness."""
    try:
        reply = data.get("assistant_reply", "")
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("No useful reply")
        value = Collaboration.model_validate(data.get("collaboration"), strict=True)
        questions = data.get("clarification_questions", [])
        if value.strategy == "execute_first" and questions:
            raise ValueError("A directly actionable task should not be gated by a questionnaire")
        if value.strategy == "verify_first" and not questions:
            raise ValueError("Critical verification needs a concrete prerequisite question")
    except (ValueError, TypeError):
        raise AppError(
            "AI_COLLABORATION_INVALID",
            "AI未生成完整的可讨论建议或必要核实项；原话和已有版本保留，可修改描述后重试。",
            502,
        ) from None


class ReplyDecoder:
    """Read only a top-level assistant_reply JSON string, including incomplete escapes.

    Raw JSON, nested fields and unterminated surrogate pairs never reach the UI.
    Values before the reply are skipped only when a complete JSON value is available.
    """

    def __init__(self, emit):
        self.emit = emit
        self.buffer = ""
        self.sent = ""
        self.decoder = json.JSONDecoder()

    def feed(self, chunk):
        if not isinstance(chunk, str):
            raise AppError("AI_SCHEMA_INVALID", "模型流格式无效。", 502)
        self.buffer += chunk
        if len(self.buffer) > 512 * 1024:
            raise AppError("AI_RESPONSE_TOO_LARGE", "模型流超过限制。", 502)
        text = self.buffer.lstrip()
        if not text.startswith("{"):
            return
        offset = 1
        while offset < len(text):
            while offset < len(text) and text[offset].isspace():
                offset += 1
            try:
                key, offset = self.decoder.raw_decode(text, offset)
            except ValueError:
                return
            if not isinstance(key, str):
                return
            while offset < len(text) and text[offset].isspace():
                offset += 1
            if offset == len(text) or text[offset] != ":":
                return
            offset += 1
            while offset < len(text) and text[offset].isspace():
                offset += 1
            if key == "assistant_reply":
                if offset == len(text) or text[offset] != '"':
                    return
                decoded = self._string_prefix(text, offset + 1)
                if len(decoded) > 12000:
                    raise AppError("AI_RESPONSE_TOO_LARGE", "AI对话回复超过限制。", 502)
                if not decoded.startswith(self.sent):
                    raise AppError("AI_SCHEMA_INVALID", "AI流片段不一致。", 502)
                delta = decoded[len(self.sent) :]
                if delta:
                    self.emit(delta)
                    self.sent = decoded
                return
            try:
                _, offset = self.decoder.raw_decode(text, offset)
            except ValueError:
                return
            while offset < len(text) and text[offset].isspace():
                offset += 1
            if offset == len(text) or text[offset] != ",":
                return
            offset += 1

    @staticmethod
    def _string_prefix(text, offset):
        result = []
        escapes = {
            '"': '"',
            "\\": "\\",
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        while offset < len(text):
            char = text[offset]
            if char == '"':
                break
            if char != "\\":
                if ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF:
                    break
                result.append(char)
                offset += 1
                continue
            if offset + 1 >= len(text):
                break
            code = text[offset + 1]
            if code in escapes:
                result.append(escapes[code])
                offset += 2
            elif code == "u":
                if offset + 6 > len(text):
                    break
                try:
                    scalar = int(text[offset + 2 : offset + 6], 16)
                except ValueError:
                    break
                if 0xD800 <= scalar <= 0xDBFF:
                    if offset + 12 > len(text) or text[offset + 6 : offset + 8] != "\\u":
                        break
                    try:
                        low = int(text[offset + 8 : offset + 12], 16)
                    except ValueError:
                        break
                    if not 0xDC00 <= low <= 0xDFFF:
                        break
                    result.append(chr(0x10000 + ((scalar - 0xD800) << 10) + low - 0xDC00))
                    offset += 12
                elif 0xDC00 <= scalar <= 0xDFFF:
                    break
                else:
                    result.append(chr(scalar))
                    offset += 6
            else:
                break
        return "".join(result)


COLLABORATION_INSTRUCTION = """
You are a collaborative assistant, not a questionnaire or a demand-field extractor.
Choose the next interaction from intent, information completeness, risk and useful actionability,
re-evaluating on every turn, even within the same task. Missing optional fields are not a reason
to withhold help. Helping with a concrete candidate is often how the user discovers their need.
Return assistant_reply FIRST in the JSON object: a natural reply in the user's language,
containing useful initial work, then at most two highest-impact questions (also in
clarification_questions). Do not ask for every unknown field.

plan_first: for open-ended but usefully actionable requests, give a discussable initial plan,
explicit assumptions, at least one option, tradeoffs, initial steps and limitations.
explore_first: when the goal itself is unclear, offer at least two concrete candidate directions
or inspirations before a short choice question; never turn the exchange into a questionnaire.
execute_first: for sufficiently clear requests, directly organize an actionable result and
next steps, with ZERO clarification_questions. Unknown nonessential details can remain unknown.
verify_first: override other strategies when safety, legal/financial decisions, irreversible
operations or missing critical prerequisites require verification; explain the missing condition,
ask necessary questions, and only give safe reversible preparation meanwhile. Do not offer
unfounded guarantees, dangerous instructions or actual irreversible execution.

collaboration contains provisional options, assumptions, estimates and next steps. It NEVER
constitutes a user requirement or confirmation. Keep suggestions out of required/preferred,
items and budget_ceiling unless grounded in the user's own words; requested shopping list
items may be extracted, but suggested purchases belong to options until explicit feedback.
Use null for unknown budget/quantity/currency. A proposed budget_estimate must be a clearly
labelled illustrative rough range with basis and uncertainty note, NEVER a quote, supplier
offer or retrieved price. Never copy estimates to the user's budget ceiling.
No product or affiliate APIs are connected. Do not invent real inventory, matching scores,
suppliers, citations, availability, price comparisons or verified sources. Clear shopping work
may prepare keywords and official search handoff only; no claim of having searched platforms.
Feedback about a prior plan iterates the same task and version, not a new unrelated intent.
Retain unchanged user requirements; distinguish confirmed_demand, unconfirmed current_draft
and provisional assistant suggestions. Needs verification is true exactly for verify_first.
The reply must not claim a plan/requirement is accepted, saved as confirmed or executed externally.
"""
