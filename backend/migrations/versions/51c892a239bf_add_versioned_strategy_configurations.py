"""add versioned strategy configurations

Revision ID: 51c892a239bf
Revises: 07a40a064895
Create Date: 2026-10-17 18:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "51c892a239bf"
down_revision: Union[str, None] = "07a40a064895"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "version", name="uq_strategy_user_version"),
    )
    op.create_index(op.f("ix_strategy_versions_user_id"), "strategy_versions", ["user_id"], unique=False)
    op.create_table(
        "strategy_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("article_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("simulated_order_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["simulated_order_id"], ["simulated_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "article_id", name="uq_strategy_user_article"),
    )
    op.create_index(op.f("ix_strategy_executions_user_id"), "strategy_executions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_strategy_executions_user_id"), table_name="strategy_executions")
    op.drop_table("strategy_executions")
    op.drop_index(op.f("ix_strategy_versions_user_id"), table_name="strategy_versions")
    op.drop_table("strategy_versions")
