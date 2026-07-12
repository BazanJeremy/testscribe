"""Raw bug report input schema — accepts minimal or structured input."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RawReport(BaseModel):
    """Minimal input accepted from any source (text, CSV, API payload)."""

    id: str | None = Field(default=None, description="Optional caller-supplied ID")
    title: str | None = Field(default=None, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    component: str | None = Field(default=None, max_length=100)
    reporter: str | None = Field(default=None, max_length=100)
    sector: str | None = Field(
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
    def normalise_sector(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalised = v.strip().lower()
        allowed = {"medtech", "fintech", "generic"}
        if normalised not in allowed:
            raise ValueError(f"sector must be one of {allowed}, got '{v}'")
        return normalised

    model_config = {"str_strip_whitespace": True}
