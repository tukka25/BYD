from datetime import datetime

from pydantic import BaseModel, Field


class UserSettingsResponse(BaseModel):
    user_id: str
    theme: str
    timezone: str
    locale: str
    default_chart_theme: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserSettingsUpdateRequest(BaseModel):
    theme: str | None = Field(default=None, max_length=50)
    timezone: str | None = Field(default=None, max_length=100)
    locale: str | None = Field(default=None, max_length=20)
    default_chart_theme: str | None = Field(default=None, max_length=50)

