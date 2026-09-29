import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversion(Base):
    __tablename__ = "conversions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # String, not UUID — matches worksheets.id (see that model's own comment on why).
    worksheet_id: Mapped[str] = mapped_column(
        String, ForeignKey("worksheets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # ondelete="CASCADE" — matches every other FK in this schema (worksheet_id above, and every
    # relationship off User/Workbook/Worksheet). Without it, a plain DELETE FROM users failed
    # with a bare FK violation the moment that user had ever requested a conversion, even though
    # deleting the same user's workbooks (which cascades worksheets -> conversions) worked fine.
    # No admin "delete user" endpoint exists yet, but this needs fixing before one does — see
    # migration d4f8c1a6e9b3.
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    worksheet: Mapped["Worksheet"] = relationship(back_populates="conversions")
    word_document: Mapped["WordDocument"] = relationship(
        back_populates="conversion", uselist=False, cascade="all, delete-orphan"
    )
