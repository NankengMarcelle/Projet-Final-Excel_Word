import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Worksheet(Base):
    __tablename__ = "worksheets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workbook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    sheet_type: Mapped[str] = mapped_column(String, default="original", nullable=False)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Bumped on any cell edit or re-sync; compared against sheet_relationships.last_synced_at
    # to cheaply detect an outdated child sheet without diffing content.
    content_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workbook: Mapped["Workbook"] = relationship(back_populates="worksheets")
    conversions: Mapped[list["Conversion"]] = relationship(
        back_populates="worksheet", cascade="all, delete-orphan"
    )
