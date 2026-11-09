"""S2 internal demand contracts, separate from the NCP wire schema."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .collaboration import Collaboration, Selection

Source = Literal["user_explicit", "model_inferred", "user_confirmed", "unknown"]
Readiness = Literal["exploring", "want", "need", "ready_to_purchase", "committed_elsewhere"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Fact(Strict):
    text: str = Field(min_length=1, max_length=500)
    source: Source
    evidence: str = Field(default="", max_length=500)
    confirmed: bool = False


class BudgetInput(Strict):
    amount: float = Field(ge=0, le=1_000_000_000_000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Budget(BudgetInput):
    source: Source
    evidence: str = Field(default="", max_length=500)
    confirmed: bool = False


BudgetBasis = Literal["unit", "line_total", "unknown"]
ItemStatus = Literal["active", "removed"]


class ShoppingItem(Strict):
    item_id: str
    name: str = Field(min_length=1, max_length=120)
    quantity: float | None = Field(default=None, gt=0, le=1_000_000)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    source: Source
    evidence: str = Field(default="", max_length=500)
    confirmed: bool = False
    required: list[Fact] = Field(default_factory=list, max_length=10)
    preferred: list[Fact] = Field(default_factory=list, max_length=10)
    unknown: list[str] = Field(default_factory=list, max_length=10)
    budget_ceiling: Budget | None = None
    budget_basis: BudgetBasis = "unknown"
    status: ItemStatus = "active"


class ItemEdits(Strict):
    item_id: str
    name: str = Field(min_length=1, max_length=120)
    quantity: float | None = Field(gt=0, le=1_000_000)
    unit: str | None = Field(min_length=1, max_length=32)
    required: list[str] = Field(max_length=10)
    preferred: list[str] = Field(max_length=10)
    unknown: list[str] = Field(max_length=10)
    budget_ceiling: BudgetInput | None
    budget_basis: BudgetBasis
    status: ItemStatus


class DemandData(Strict):
    assistant_reply: str = Field(default="", max_length=12000)
    collaboration: Collaboration | None = None
    solution_selection: Selection | None = None
    solution_confirmed: bool = False
    items: list[ShoppingItem] = Field(default_factory=list, max_length=30)
    desired_outcome: str = Field(min_length=1, max_length=1000)
    required: list[Fact] = Field(max_length=30)
    preferred: list[Fact] = Field(max_length=30)
    unknown: list[str] = Field(max_length=30)
    budget_ceiling: Budget | None = None
    readiness: Readiness = "exploring"
    alternatives_acceptable: bool | None = None
    clarification_questions: list[str] = Field(default_factory=list, max_length=2)
    possible_new_intent: bool = False


class Edits(Strict):
    items: list[ItemEdits] | None = Field(default=None, max_length=30)
    desired_outcome: str = Field(min_length=1, max_length=1000)
    required: list[str] = Field(max_length=30)
    preferred: list[str] = Field(max_length=30)
    unknown: list[str] = Field(max_length=30)
    budget_ceiling: BudgetInput | None = None
    readiness: Readiness
    alternatives_acceptable: bool


class ParseRequest(Strict):
    message_id: str
    expected_version_id: str | None
    request_id: str
    consent: bool = False
    config_id: str | None = None


class ConfirmRequest(Strict):
    selected_option_id: str | None = Field(default=None, max_length=40)
    confirm_solution: bool = False
    version_id: str
    request_id: str
    confirm: bool = False
    continue_current_intent: bool = False
    edits: Edits


class WithdrawRequest(Strict):
    request_id: str
    expected_version_id: str
    confirm: bool = False
    reason: str = Field(default="", max_length=500)


class ExportRequest(Strict):
    acknowledge_private_export: bool = False
