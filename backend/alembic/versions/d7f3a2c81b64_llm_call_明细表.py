"""llm_call: LLM 调用明细表（逐次尝试的输入/输出/修复链/耗时/用量）

Revision ID: d7f3a2c81b64
Revises: c4a7e91b2d3f
Create Date: 2026-10-14
"""

from alembic import op
import sqlalchemy as sa


revision = "d7f3a2c81b64"
down_revision = "c4a7e91b2d3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_call",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("call_index", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=50), nullable=True),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error_kind", sa.String(length=30), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("request_messages", sa.JSON(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_call")),
    )
    with op.batch_alter_table("llm_call", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_llm_call_job_id"), ["job_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_call_operation"), ["operation"], unique=False)
        batch_op.create_index(batch_op.f("ix_llm_call_ts"), ["ts"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("llm_call", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_llm_call_ts"))
        batch_op.drop_index(batch_op.f("ix_llm_call_operation"))
        batch_op.drop_index(batch_op.f("ix_llm_call_job_id"))
    op.drop_table("llm_call")
