from datetime import datetime

from pydantic import BaseModel, Field


class DashboardCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    data_source_ids: list[str] = Field(default_factory=list)


class DashboardUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    data_source_ids: list[str] | None = None


class DashboardResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: str | None
    data_source_ids: list[str]
    created_at: datetime
    updated_at: datetime

