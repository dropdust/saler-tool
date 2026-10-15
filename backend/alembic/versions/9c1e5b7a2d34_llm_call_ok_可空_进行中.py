"""llm_call.ok 可空：进行中（请求已发出、尚未返回）与失败可分辨

明细行在请求发出时先落库（ok=NULL），返回后原位收口为成功/失败——卡住时据此
判断阻塞在哪一步（见 providers/llm/call_log.py）。

Revision ID: 9c1e5b7a2d34
Revises: d7f3a2c81b64
Create Date: 2026-10-15
"""

from alembic import op
import sqlalchemy as sa


revision = "9c1e5b7a2d34"
down_revision = "d7f3a2c81b64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_call", schema=None) as batch_op:
        batch_op.alter_column("ok", existing_type=sa.Boolean(), nullable=True)


def downgrade() -> None:
    # 先给"进行中"行一个确定的取值，否则无法恢复 NOT NULL
    op.execute("UPDATE llm_call SET ok = 0 WHERE ok IS NULL")
    with op.batch_alter_table("llm_call", schema=None) as batch_op:
        batch_op.alter_column("ok", existing_type=sa.Boolean(), nullable=False)
