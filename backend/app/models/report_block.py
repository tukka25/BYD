import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BlockKind(str, enum.Enum):
    CHART = "chart"
    METRIC = "metric"
    TEXT = "text"


class ReportBlock(Base):
    """One block on a report canvas: a chart, a metric, or a note.

    A NEW table rather than a column on `dashboards`, deliberately. The app
    creates its schema with `Base.metadata.create_all`, which creates missing
    tables but never alters existing ones — adding a column here would silently
    not exist on any database that already ran, and the failure would surface as
    a query error at runtime.

    A chart block stores what produced it as well as the result: the question,
    the generated program, and the figure. That is the product's claim made
    durable — the chart is kept beside the code that drew it, so it can be shown
    rather than taken on trust.
    """

    __tablename__ = "report_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dashboard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[BlockKind] = mapped_column(Enum(BlockKind), default=BlockKind.CHART, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # What was asked, what ran, and what came back.
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    figure_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chart_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # True only on blocks saved before 2026-11-23, when a hardcoded backup chart
    # could stand in for the model's. Nothing sets it now; it stays so those old
    # blocks keep their label in the UI rather than passing as the model's.
    used_fallback: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Grid position, in grid units.
    x: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    y: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    w: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    h: Mapped[int] = mapped_column(Integer, default=8, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    dashboard = relationship("Dashboard", backref="blocks")
