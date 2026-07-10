"""Strict structured contract for the persisted full-company AI verdict."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ChecklistId = Literal[
    "revenue_growth",
    "gross_margin_trend",
    "operating_leverage",
    "profit_quality",
    "valuation_vs_history",
    "catalyst",
    "margin_of_safety",
    "small_cap",
    "balance_sheet",
    "dividend",
    "framing",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Catalyst(StrictModel):
    type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    priced_in: Literal["tak", "nie", "częściowo", "nieznane"]


class ChecklistItem(StrictModel):
    id: ChecklistId
    item: str = Field(min_length=1)
    verdict: Literal["spełnia", "nie spełnia", "nieznane"]
    evidence: str = Field(min_length=1)


class ForumInsight(StrictModel):
    claim: str = Field(min_length=1)
    confidence: Literal["low", "medium", "high"]
    post_ids: list[int]


class Potential(StrictModel):
    upside: str = Field(min_length=1)
    downside: str = Field(min_length=1)


class Scenario(StrictModel):
    kind: Literal["negative", "base", "positive", "event"]
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    key_drivers: list[str] = Field(min_length=2)
    watch_items: list[str] = Field(min_length=2)
    probability: str = Field(min_length=1)


class VerifyNext(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    why: str = Field(min_length=1)


class AnalysisVerdict(StrictModel):
    thesis: str = Field(min_length=1)
    catalysts: list[Catalyst]
    checklist: list[ChecklistItem]
    red_flags: list[str]
    one_off_risk: str = Field(min_length=1)
    forum_insights: list[ForumInsight]
    # Provider output includes a proposed score for backward compatibility, but
    # the API overwrites it with analysis_scoring.compute_alignment_score.
    alignment_score: int = Field(ge=0, le=100)
    potential: Potential
    scenarios: list[Scenario] = Field(min_length=3)
    verify_next: list[VerifyNext]
    summary_pl: str = Field(min_length=1)

    @model_validator(mode="after")
    def checklist_ids_are_unique(self):
        ids = [item.id for item in self.checklist]
        if len(ids) != len(set(ids)):
            raise ValueError("checklist ids must be unique")
        kinds = {scenario.kind for scenario in self.scenarios}
        missing = {"negative", "base", "positive"} - kinds
        if missing:
            raise ValueError(
                "scenarios missing kinds: " + ", ".join(sorted(missing))
            )
        return self
