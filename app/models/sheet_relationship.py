import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SheetRelationship(Base):
    __tablename__ = "sheet_relationships"
    __table_args__ = (
        CheckConstraint("parent_worksheet_id != child_worksheet_id", name="ck_parent_ne_child"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_worksheet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("worksheets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_worksheet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worksheets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Ordered list of column headers, e.g. ["Name", "Status", "Amount"]
    selected_columns: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Nested AND/OR condition tree, see docs/plan for the shape
    filter_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
