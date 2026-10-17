"""add currency-aware metadata to the shared paper ledger

Revision ID: b37f90e2a64f
Revises: 51c892a239bf
Create Date: 2026-10-17 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b37f90e2a64f"
down_revision: Union[str, None] = "51c892a239bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("virtual_positions") as batch_op:
        batch_op.add_column(sa.Column("market_type", sa.String(length=8), server_default="EQUITY", nullable=False))
        batch_op.add_column(sa.Column("base_currency", sa.String(length=3), nullable=True))
        batch_op.add_column(sa.Column("quote_currency", sa.String(length=3), server_default="INR", nullable=False))
        batch_op.add_column(sa.Column("average_entry_inr", sa.Numeric(precision=18, scale=8), nullable=True))
        batch_op.alter_column("symbol", existing_type=sa.String(length=20), type_=sa.String(length=32), existing_nullable=False)
        batch_op.alter_column("average_entry", existing_type=sa.Numeric(precision=18, scale=4), type_=sa.Numeric(precision=18, scale=8), existing_nullable=False)

    with op.batch_alter_table("simulated_orders") as batch_op:
        batch_op.add_column(sa.Column("market_type", sa.String(length=8), server_default="EQUITY", nullable=False))
        batch_op.add_column(sa.Column("base_currency", sa.String(length=3), nullable=True))
        batch_op.add_column(sa.Column("quote_currency", sa.String(length=3), server_default="INR", nullable=False))
        batch_op.add_column(sa.Column("conversion_rate", sa.Numeric(precision=18, scale=8), server_default="1", nullable=False))
        batch_op.add_column(sa.Column("value_inr", sa.Numeric(precision=18, scale=2), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("bid", sa.Numeric(precision=18, scale=8), nullable=True))
        batch_op.add_column(sa.Column("ask", sa.Numeric(precision=18, scale=8), nullable=True))
        batch_op.add_column(sa.Column("source_provider", sa.String(length=80), server_default="legacy", nullable=False))
        batch_op.add_column(sa.Column("price_basis", sa.String(length=40), server_default="legacy fill", nullable=False))
        batch_op.add_column(sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column("symbol", existing_type=sa.String(length=20), type_=sa.String(length=32), existing_nullable=False)
        batch_op.alter_column("quote_price", existing_type=sa.Numeric(precision=18, scale=4), type_=sa.Numeric(precision=18, scale=8), existing_nullable=False)
        batch_op.alter_column("fill_price", existing_type=sa.Numeric(precision=18, scale=4), type_=sa.Numeric(precision=18, scale=8), existing_nullable=False)

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE virtual_positions SET average_entry_inr = average_entry WHERE average_entry_inr IS NULL"))
    connection.execute(sa.text("UPDATE simulated_orders SET value_inr = fill_price * quantity WHERE value_inr = 0"))
    connection.execute(sa.text("UPDATE simulated_orders SET source_provider = 'synthetic-demo', price_basis = 'synthetic demo value' WHERE source_provider = 'legacy'"))


def downgrade() -> None:
    with op.batch_alter_table("simulated_orders") as batch_op:
        batch_op.alter_column("fill_price", existing_type=sa.Numeric(precision=18, scale=8), type_=sa.Numeric(precision=18, scale=4), existing_nullable=False)
        batch_op.alter_column("quote_price", existing_type=sa.Numeric(precision=18, scale=8), type_=sa.Numeric(precision=18, scale=4), existing_nullable=False)
        batch_op.alter_column("symbol", existing_type=sa.String(length=32), type_=sa.String(length=20), existing_nullable=False)
        batch_op.drop_column("source_timestamp")
        batch_op.drop_column("price_basis")
        batch_op.drop_column("source_provider")
        batch_op.drop_column("ask")
        batch_op.drop_column("bid")
        batch_op.drop_column("value_inr")
        batch_op.drop_column("conversion_rate")
        batch_op.drop_column("quote_currency")
        batch_op.drop_column("base_currency")
        batch_op.drop_column("market_type")

    with op.batch_alter_table("virtual_positions") as batch_op:
        batch_op.alter_column("average_entry", existing_type=sa.Numeric(precision=18, scale=8), type_=sa.Numeric(precision=18, scale=4), existing_nullable=False)
        batch_op.alter_column("symbol", existing_type=sa.String(length=32), type_=sa.String(length=20), existing_nullable=False)
        batch_op.drop_column("average_entry_inr")
        batch_op.drop_column("quote_currency")
        batch_op.drop_column("base_currency")
        batch_op.drop_column("market_type")
