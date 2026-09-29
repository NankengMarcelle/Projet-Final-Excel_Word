"""cascade conversion requester delete

Revision ID: d4f8c1a6e9b3
Revises: 5f3a8b2c1d90
Create Date: 2026-09-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4f8c1a6e9b3'
down_revision: Union[str, Sequence[str], None] = '5f3a8b2c1d90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # conversions.requested_by_id -> users.id had no ondelete behavior at all (unlike every
    # other FK in this schema) — a plain DELETE FROM users raised a bare FK violation if that
    # user had ever requested a conversion. Postgres has no ALTER CONSTRAINT for ON DELETE, so
    # this drops and recreates the constraint under its existing default-generated name.
    op.drop_constraint('conversions_requested_by_id_fkey', 'conversions', type_='foreignkey')
    op.create_foreign_key(
        'conversions_requested_by_id_fkey',
        'conversions',
        'users',
        ['requested_by_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('conversions_requested_by_id_fkey', 'conversions', type_='foreignkey')
    op.create_foreign_key(
        'conversions_requested_by_id_fkey',
        'conversions',
        'users',
        ['requested_by_id'],
        ['id'],
    )
