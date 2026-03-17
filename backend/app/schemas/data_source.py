from datetime import datetime

from pydantic import BaseModel, Field

from app.models.data_source import DataSourceStatus, DataSourceType


class DataSourceResponse(BaseModel):
    id: str
    user_id: str
    source_type: DataSourceType
    status: DataSourceStatus
    display_name: str

    file_path: str | None = None
    original_filename: str | None = None
    file_extension: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None

    db_type: str | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    db_username: str | None = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DataSourceDBCreateRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=255)
    db_type: str = Field(min_length=2, max_length=50)
    db_host: str = Field(min_length=2, max_length=255)
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(min_length=1, max_length=255)
    db_username: str = Field(min_length=1, max_length=255)
    db_password: str = Field(min_length=1, max_length=255)

