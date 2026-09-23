"""relax worksheets.id from UUID to a plain string

Univer generates its own id for a sheet the instant it's created via its native "+" add-sheet
button — a short random string (Math.random().toString(36).substring(2,8), e.g. "k3j9x2"),
never a real UUID. Keeping worksheets.id a strict UUID column meant a locally-created sheet
could never be persisted with the id Univer already assigned it: the app would either have to
reject Univer's own id and remap it after the fact (fighting Univer's own live model, which
owns everything past creation the same way it owns deletes and edits), or relax the column.
Existing rows are untouched in content (a real UUID's own text form is still a valid string;
this widens what's *allowed* going forward, it doesn't rewrite anything).

Revision ID: 5f3a8b2c1d90
Revises: a1b2c3d4e5f6
Create Date: 2026-09-22 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f3a8b2c1d90'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres won't let a referenced column's type change while a dependent FK constraint
    # still exists, even converting to a type compatible on both sides — drop first, recreate
    # after. Same for the CHECK constraint: it compares parent_worksheet_id <> child_worksheet_id
    # directly, and Postgres validates it against each column's *new* type as soon as either one
    # changes — altering them one at a time (as op.alter_column necessarily does) briefly leaves
    # a varchar <> uuid comparison with no defined operator, so this has to go too, not just the
    # FKs.
    op.drop_constraint('ck_parent_ne_child', 'sheet_relationships', type_='check')
    op.drop_constraint('sheet_relationships_parent_worksheet_id_fkey', 'sheet_relationships', type_='foreignkey')
    op.drop_constraint('sheet_relationships_child_worksheet_id_fkey', 'sheet_relationships', type_='foreignkey')
    op.drop_constraint('conversions_worksheet_id_fkey', 'conversions', type_='foreignkey')

    op.alter_column(
        'worksheets', 'id', existing_type=sa.UUID(), type_=sa.String(), postgresql_using='id::text'
    )
    op.alter_column(
        'sheet_relationships', 'parent_worksheet_id',
        existing_type=sa.UUID(), type_=sa.String(), postgresql_using='parent_worksheet_id::text',
    )
    op.alter_column(
        'sheet_relationships', 'child_worksheet_id',
        existing_type=sa.UUID(), type_=sa.String(), postgresql_using='child_worksheet_id::text',
    )
    op.alter_column(
        'conversions', 'worksheet_id',
        existing_type=sa.UUID(), type_=sa.String(), postgresql_using='worksheet_id::text',
    )

    op.create_foreign_key(
        'sheet_relationships_parent_worksheet_id_fkey', 'sheet_relationships', 'worksheets',
        ['parent_worksheet_id'], ['id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'sheet_relationships_child_worksheet_id_fkey', 'sheet_relationships', 'worksheets',
        ['child_worksheet_id'], ['id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'conversions_worksheet_id_fkey', 'conversions', 'worksheets',
        ['worksheet_id'], ['id'], ondelete='CASCADE',
    )
    op.create_check_constraint(
        'ck_parent_ne_child', 'sheet_relationships', 'parent_worksheet_id != child_worksheet_id'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Fails if any worksheet id created since the upgrade isn't valid UUID text (e.g. a sheet
    # Univer created natively) — expected: this direction can't losslessly narrow the type back.
    op.drop_constraint('ck_parent_ne_child', 'sheet_relationships', type_='check')
    op.drop_constraint('sheet_relationships_parent_worksheet_id_fkey', 'sheet_relationships', type_='foreignkey')
    op.drop_constraint('sheet_relationships_child_worksheet_id_fkey', 'sheet_relationships', type_='foreignkey')
    op.drop_constraint('conversions_worksheet_id_fkey', 'conversions', type_='foreignkey')

    op.alter_column(
        'worksheets', 'id', existing_type=sa.String(), type_=sa.UUID(), postgresql_using='id::uuid'
    )
    op.alter_column(
        'sheet_relationships', 'parent_worksheet_id',
        existing_type=sa.String(), type_=sa.UUID(), postgresql_using='parent_worksheet_id::uuid',
    )
    op.alter_column(
        'sheet_relationships', 'child_worksheet_id',
        existing_type=sa.String(), type_=sa.UUID(), postgresql_using='child_worksheet_id::uuid',
    )
    op.alter_column(
        'conversions', 'worksheet_id',
        existing_type=sa.String(), type_=sa.UUID(), postgresql_using='worksheet_id::uuid',
    )

    op.create_foreign_key(
        'sheet_relationships_parent_worksheet_id_fkey', 'sheet_relationships', 'worksheets',
        ['parent_worksheet_id'], ['id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'sheet_relationships_child_worksheet_id_fkey', 'sheet_relationships', 'worksheets',
        ['child_worksheet_id'], ['id'], ondelete='CASCADE',
    )
    op.create_foreign_key(
        'conversions_worksheet_id_fkey', 'conversions', 'worksheets',
        ['worksheet_id'], ['id'], ondelete='CASCADE',
    )
    op.create_check_constraint(
        'ck_parent_ne_child', 'sheet_relationships', 'parent_worksheet_id != child_worksheet_id'
    )
