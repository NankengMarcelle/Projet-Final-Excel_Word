import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
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
    # No longer unique: multi-sheet extraction lets several relationships (one per contributing
    # source sheet) share the same child_worksheet_id — see migration a1b2c3d4e5f6.
    child_worksheet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worksheets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Ordered list of 1-indexed column numbers, e.g. [1, 2, 4] — not header names. A real
    # multi-row-header matrix sheet can have the same leaf label appear under multiple group
    # headers (e.g. "AE voté" under both "Prévision 2026" and "Prévision 2027"), so column
    # identity has to be positional; header text is only ever a display label, never a key.
    selected_columns: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Nested AND/OR condition tree; each condition's "column" is a 1-indexed column number,
    # same reasoning as selected_columns above.
    filter_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Inclusive 1-indexed row range of the parent sheet's header block (a real matrix sheet's
    # header commonly spans more than one row — e.g. a "Prévision 2026" group label in one row
    # with "AE voté"/"CP voté" sub-labels in the row below). header_start_row == header_end_row
    # for a plain single-row header.
    header_start_row: Mapped[int] = mapped_column(Integer, nullable=False)
    header_end_row: Mapped[int] = mapped_column(Integer, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
