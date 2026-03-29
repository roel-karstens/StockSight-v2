"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # stocks
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("sector", sa.String(100)),
        sa.Column("industry", sa.String(100)),
        sa.Column("country", sa.String(100)),
        sa.Column("exchange", sa.String(50)),
        sa.Column("currency", sa.String(10)),
        sa.Column("market_cap", sa.Float()),
        sa.Column("market_cap_category", sa.String(20)),
        sa.Column("description", sa.Text()),
        sa.Column("website", sa.String(255)),
        sa.Column("last_updated", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # fundamentals
    op.create_table(
        "fundamentals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), sa.ForeignKey("stocks.ticker"), index=True, nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        # Quality criteria
        sa.Column("roce", sa.Float()),
        sa.Column("revenue_growth", sa.Float()),
        sa.Column("fcf_growth", sa.Float()),
        sa.Column("eps_growth", sa.Float()),
        sa.Column("lt_debt_to_fcf", sa.Float()),
        sa.Column("peg_ratio", sa.Float()),
        # Raw financials
        sa.Column("revenue", sa.Float()),
        sa.Column("gross_profit", sa.Float()),
        sa.Column("operating_income", sa.Float()),
        sa.Column("net_income", sa.Float()),
        sa.Column("ebitda", sa.Float()),
        sa.Column("free_cash_flow", sa.Float()),
        sa.Column("capital_employed", sa.Float()),
        sa.Column("total_debt", sa.Float()),
        sa.Column("long_term_debt", sa.Float()),
        sa.Column("cash_and_equivalents", sa.Float()),
        sa.Column("shares_outstanding", sa.Float()),
        sa.Column("eps", sa.Float()),
        sa.Column("book_value_per_share", sa.Float()),
        sa.Column("dividend_per_share", sa.Float()),
        # Valuation
        sa.Column("pe_ratio", sa.Float()),
        sa.Column("ps_ratio", sa.Float()),
        sa.Column("pb_ratio", sa.Float()),
        sa.Column("ev_ebitda", sa.Float()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "fiscal_year"),
    )

    # prices
    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), sa.ForeignKey("stocks.ticker"), index=True, nullable=False),
        sa.Column("price_date", sa.Date(), index=True, nullable=False),
        sa.Column("open", sa.Float()),
        sa.Column("high", sa.Float()),
        sa.Column("low", sa.Float()),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("adj_close", sa.Float()),
        sa.Column("volume", sa.Integer()),
        sa.UniqueConstraint("ticker", "price_date"),
    )

    # portfolio_holdings
    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), sa.ForeignKey("stocks.ticker"), index=True, nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("avg_buy_price", sa.Float(), nullable=False),
        sa.Column("buy_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # portfolio_snapshots
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.Date(), unique=True, index=True, nullable=False),
        sa.Column("total_value", sa.Float(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("holdings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("portfolio_snapshots")
    op.drop_table("portfolio_holdings")
    op.drop_table("prices")
    op.drop_table("fundamentals")
    op.drop_table("stocks")
