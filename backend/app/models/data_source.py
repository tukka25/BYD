import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DataSourceType(str, enum.Enum):
    FILE = "file"
    DB = "db"


class DataSourceStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[DataSourceType] = mapped_column(Enum(DataSourceType), nullable=False)
    status: Mapped[DataSourceStatus] = mapped_column(
        Enum(DataSourceStatus), default=DataSourceStatus.ACTIVE, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    db_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    db_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    db_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="data_sources")
    dashboards = relationship(
        "Dashboard",
        secondary="dashboard_data_sources",
        back_populates="data_sources",
    )
