"""Structured output for the Campus Customs vendor desk agent."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class VendorRecommendation(BaseModel):
    """The agent's recommendation for one vendor document.

    A field is null when the document does not state that fact (handbook section 4:
    "report it as unknown. Never guess a number").
    """

    vendor: str | None = Field(
        description="Vendor company name as given in the document; null if not stated.",
        min_length=1,
    )
    sku: str | None = Field(
        description="Campus Customs SKU, format CC-XX-000; null if not stated.",
        pattern=r"^CC-[A-Z]{2}-\d{3}$",
    )
    unit_price: float | None = Field(
        description="Quoted price per unit in US dollars; null if not stated.",
        gt=0,
    )
    lead_time_days: int | None = Field(
        description="Lead time in whole days, as the vendor states it; null if not stated.",
        ge=0,
    )
    min_order: int | None = Field(
        description="Minimum order in units; null if not stated.",
        ge=1,
    )
    decision: Literal["recommend", "do_not_recommend"] = Field(
        description="recommend only if all four handbook purchasing checks pass.",
    )
    reason: str = Field(
        description="One sentence naming the purchasing check that decided the outcome.",
        min_length=10,
        max_length=400,
    )

    @field_validator("reason")
    @classmethod
    def single_line(cls, value: str) -> str:
        value = value.strip()
        if "\n" in value:
            raise ValueError("reason must be a single sentence on one line")
        return value
