"""
schemas.py — Pydantic request/response models for the StockSight API.

All schemas per spec-backend-api.md.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stock Schemas
# ---------------------------------------------------------------------------


class StockBase(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    exchange: str | None = None
    currency: str | None = None
    market_cap: float | None = None
    market_cap_category: str | None = None  # mega/large/mid/small/micro


class StockOut(StockBase):
    id: int
    description: str | None = None
    website: str | None = None
    last_updated: datetime | None = None

    model_config = {"from_attributes": True}


class StockSearchResult(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    country: str | None = None
    market_cap_category: str | None = None
    quality_score: int = 0  # 0–6, from latest 3yr avg


# ---------------------------------------------------------------------------
# Fundamental Schemas
# ---------------------------------------------------------------------------


class FundamentalOut(BaseModel):
    fiscal_year: int
    roce: float | None = None
    revenue_growth: float | None = None  # decimal, e.g. 0.148
    fcf_growth: float | None = None
    eps_growth: float | None = None
    lt_debt_to_fcf: float | None = None
    peg_ratio: float | None = None
    revenue: float | None = None
    free_cash_flow: float | None = None
    net_income: float | None = None
    eps: float | None = None
    pe_ratio: float | None = None
    shares_outstanding: float | None = None
    long_term_debt: float | None = None

    model_config = {"from_attributes": True}


class QualityCriteria(BaseModel):
    roce_ok: bool = False
    revenue_growth_ok: bool = False
    fcf_growth_ok: bool = False
    eps_growth_ok: bool = False
    lt_debt_fcf_ok: bool = False
    peg_ok: bool = False
    score: int = 0  # 0–6


class StockFundamentalsResponse(BaseModel):
    ticker: str
    name: str | None = None
    fundamentals: list[FundamentalOut]
    avg_3yr: QualityCriteria
    avg_10yr: QualityCriteria


# ---------------------------------------------------------------------------
# Price Schemas
# ---------------------------------------------------------------------------


class PricePoint(BaseModel):
    date: date
    close: float
    adj_close: float | None = None
    volume: int | None = None


class PriceHistoryResponse(BaseModel):
    ticker: str
    prices: list[PricePoint]


# ---------------------------------------------------------------------------
# DCF Schemas
# ---------------------------------------------------------------------------


class DCFInputSchema(BaseModel):
    wacc: float = Field(0.10, ge=0.01, le=0.50)
    terminal_growth: float = Field(0.03, ge=0.00, le=0.10)
    fcf_growth_years_1_5: float = Field(0.15, ge=-0.50, le=1.00)
    fcf_growth_years_6_10: float = Field(0.08, ge=-0.50, le=1.00)
    years: int = Field(10, ge=5, le=20)


class DCFOutputSchema(BaseModel):
    intrinsic_value_per_share: float
    current_price: float | None = None
    margin_of_safety: float | None = None  # percent
    projected_fcfs: list[dict]  # [{year, fcf, pv, growth_rate}]
    terminal_value: float
    total_pv: float


class ReverseDCFOutputSchema(BaseModel):
    implied_growth_rate: float
    current_price: float
    wacc: float
    sensitivity: list[dict]  # [{growth_rate, implied_price}]


# ---------------------------------------------------------------------------
# Portfolio Schemas
# ---------------------------------------------------------------------------


class HoldingCreate(BaseModel):
    ticker: str
    shares: float = Field(gt=0)
    avg_buy_price: float = Field(gt=0)
    buy_date: date
    notes: str | None = None


class HoldingUpdate(BaseModel):
    shares: float | None = Field(None, gt=0)
    avg_buy_price: float | None = Field(None, gt=0)
    buy_date: date | None = None
    notes: str | None = None


class HoldingOut(BaseModel):
    id: int
    ticker: str
    name: str | None = None
    shares: float
    avg_buy_price: float
    buy_date: date
    notes: str | None = None
    current_price: float | None = None
    current_value: float | None = None
    total_cost: float | None = None
    unrealised_pnl: float | None = None
    unrealised_pnl_pct: float | None = None
    sector: str | None = None
    country: str | None = None
    market_cap_category: str | None = None

    model_config = {"from_attributes": True}


class AllocationItem(BaseModel):
    label: str
    value: float  # USD
    percentage: float


class PortfolioAllocations(BaseModel):
    by_country: list[AllocationItem]
    by_sector: list[AllocationItem]
    by_market_cap: list[AllocationItem]
    by_holding: list[AllocationItem]


class PortfolioPerformancePoint(BaseModel):
    date: date
    portfolio_value: float
    benchmark_value: float


class PortfolioStats(BaseModel):
    total_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    beta: float | None = None
    num_holdings: int
    quality_score_avg: float | None = None
