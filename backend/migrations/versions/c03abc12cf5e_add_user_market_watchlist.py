"""add user-scoped normalized market watchlists

Revision ID: c03abc12cf5e
Revises: b37f90e2a64f
Create Date: 2026-10-17 20:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c03abc12cf5e"
down_revision: Union[str, None] = "b37f90e2a64f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "market_watchlist",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("market_type", sa.String(length=8), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=True),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "market_type", "symbol", name="uq_watchlist_user_market_symbol"),
    )
    op.create_index(op.f("ix_market_watchlist_user_id"), "market_watchlist", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_market_watchlist_user_id"), table_name="market_watchlist")
    op.drop_table("market_watchlist")
