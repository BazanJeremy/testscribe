"""Raw bug report input schema — accepts minimal or structured input."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class RawReport(BaseModel):
    """Minimal input accepted from any source (text, CSV, API payload)."""

    id: Optional[str] = Field(default=None, description="Optional caller-supplied ID")
    title: Optional[str] = Field(default=None, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    component: Optional[str] = Field(default=None, max_length=100)
    reporter: Optional[str] = Field(default=None, max_length=100)
    sector: Optional[str] = Field(
        default=None,
        description="Sector hint: 'medtech', 'fintech', or 'generic'",
    )

    @field_validator("description")
    @classmethod
    def strip_and_require(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("description cannot be empty or whitespace only")
        return v

    @field_validator("sector")
    @classmethod
    def normalise_sector(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalised = v.strip().lower()
        allowed = {"medtech", "fintech", "generic"}
        if normalised not in allowed:
            raise ValueError(f"sector must be one of {allowed}, got '{v}'")
        return normalised

    model_config = {"str_strip_whitespace": True}
