"""allow multiple parents per child sheet

Revision ID: a1b2c3d4e5f6
Revises: fd27237322e0
Create Date: 2026-09-21 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fd27237322e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # child_worksheet_id was unique — one parent per child. Multi-sheet extraction needs several
    # SheetRelationship rows (one per contributing source sheet) to share the same child, so this
    # relaxes it to a plain (non-unique) index — still useful for the same lookups, just no
    # longer enforcing at most one row per child.
    op.drop_index('ix_sheet_relationships_child_worksheet_id', table_name='sheet_relationships')
    op.create_index(
        op.f('ix_sheet_relationships_child_worksheet_id'),
        'sheet_relationships',
        ['child_worksheet_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sheet_relationships_child_worksheet_id'), table_name='sheet_relationships')
    op.create_index(
        'ix_sheet_relationships_child_worksheet_id',
        'sheet_relationships',
        ['child_worksheet_id'],
        unique=True,
    )
