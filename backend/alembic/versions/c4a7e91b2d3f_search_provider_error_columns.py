"""search_provider: +last_error_kind / +last_error_at（004 R9 运行时失败可见性）

Revision ID: c4a7e91b2d3f
Revises: 80e843b63e22
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4a7e91b2d3f'
down_revision = '80e843b63e22'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('search_provider', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_error_kind', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('search_provider', schema=None) as batch_op:
        batch_op.drop_column('last_error_at')
        batch_op.drop_column('last_error_kind')
