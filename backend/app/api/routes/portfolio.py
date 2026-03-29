"""
portfolio.py — FastAPI routes for portfolio management endpoints.

All 7 portfolio endpoints per spec-backend-api.md:
  GET    /portfolio/holdings
  POST   /portfolio/holdings
  PUT    /portfolio/holdings/{id}
  DELETE /portfolio/holdings/{id}
  GET    /portfolio/stats
  GET    /portfolio/allocations
  GET    /portfolio/performance
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.session import get_db
from app.models.models import PortfolioHolding, PortfolioSnapshot, Price, Stock
from app.schemas.schemas import (
    AllocationItem,
    HoldingCreate,
    HoldingOut,
    HoldingUpdate,
    PortfolioAllocations,
    PortfolioPerformancePoint,
    PortfolioStats,
)
from app.services.data_fetcher import fetch_price_history, fetch_stock_info

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _get_current_price(ticker: str, db: AsyncSession) -> float | None:
    """Get the latest price for a ticker from the prices table."""
    result = await db.execute(
        select(Price)
        .where(Price.ticker == ticker)
        .order_by(Price.price_date.desc())
        .limit(1)
    )
    price = result.scalar_one_or_none()
    return price.close if price else None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/holdings", response_model=list[HoldingOut])
async def list_holdings(db: AsyncSession = Depends(get_db)):
    """List all active portfolio holdings with live P&L."""
    result = await db.execute(
        select(PortfolioHolding)
        .options(joinedload(PortfolioHolding.stock))
        .where(PortfolioHolding.is_active == True)  # noqa: E712
        .order_by(PortfolioHolding.buy_date.desc())
    )
    holdings = result.scalars().unique().all()

    output: list[dict] = []
    for h in holdings:
        current_price = await _get_current_price(h.ticker, db)
        total_cost = h.shares * h.avg_buy_price
        current_value = h.shares * current_price if current_price else None
        unrealised_pnl = (current_value - total_cost) if current_value is not None else None
        unrealised_pnl_pct = (
            (unrealised_pnl / total_cost * 100) if unrealised_pnl is not None and total_cost > 0 else None
        )

        output.append(
            {
                "id": h.id,
                "ticker": h.ticker,
                "name": h.stock.name if h.stock else None,
                "shares": h.shares,
                "avg_buy_price": h.avg_buy_price,
                "buy_date": h.buy_date,
                "notes": h.notes,
                "current_price": current_price,
                "current_value": round(current_value, 2) if current_value else None,
                "total_cost": round(total_cost, 2),
                "unrealised_pnl": round(unrealised_pnl, 2) if unrealised_pnl is not None else None,
                "unrealised_pnl_pct": round(unrealised_pnl_pct, 2) if unrealised_pnl_pct is not None else None,
                "sector": h.stock.sector if h.stock else None,
                "country": h.stock.country if h.stock else None,
                "market_cap_category": h.stock.market_cap_category if h.stock else None,
            }
        )

    return output


@router.post("/holdings", response_model=HoldingOut)
async def add_holding(
    payload: HoldingCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new holding to the portfolio."""
    ticker = payload.ticker.upper()

    # Ensure stock exists in DB
    from app.api.routes.stocks import _get_or_create_stock

    stock = await _get_or_create_stock(ticker, db)

    holding = PortfolioHolding(
        ticker=ticker,
        shares=payload.shares,
        avg_buy_price=payload.avg_buy_price,
        buy_date=payload.buy_date,
        notes=payload.notes,
    )
    db.add(holding)
    await db.flush()

    # Compute live fields
    current_price = await _get_current_price(ticker, db)
    total_cost = holding.shares * holding.avg_buy_price
    current_value = holding.shares * current_price if current_price else None
    unrealised_pnl = (current_value - total_cost) if current_value is not None else None
    unrealised_pnl_pct = (
        (unrealised_pnl / total_cost * 100) if unrealised_pnl is not None and total_cost > 0 else None
    )

    return {
        "id": holding.id,
        "ticker": holding.ticker,
        "name": stock.name,
        "shares": holding.shares,
        "avg_buy_price": holding.avg_buy_price,
        "buy_date": holding.buy_date,
        "notes": holding.notes,
        "current_price": current_price,
        "current_value": round(current_value, 2) if current_value else None,
        "total_cost": round(total_cost, 2),
        "unrealised_pnl": round(unrealised_pnl, 2) if unrealised_pnl is not None else None,
        "unrealised_pnl_pct": round(unrealised_pnl_pct, 2) if unrealised_pnl_pct is not None else None,
        "sector": stock.sector,
        "country": stock.country,
        "market_cap_category": stock.market_cap_category,
    }


@router.put("/holdings/{holding_id}", response_model=HoldingOut)
async def update_holding(
    holding_id: int,
    payload: HoldingUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing holding."""
    result = await db.execute(
        select(PortfolioHolding)
        .options(joinedload(PortfolioHolding.stock))
        .where(PortfolioHolding.id == holding_id)
    )
    holding = result.scalar_one_or_none()

    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")

    # Update only non-None fields
    if payload.shares is not None:
        holding.shares = payload.shares
    if payload.avg_buy_price is not None:
        holding.avg_buy_price = payload.avg_buy_price
    if payload.buy_date is not None:
        holding.buy_date = payload.buy_date
    if payload.notes is not None:
        holding.notes = payload.notes

    await db.flush()

    # Recompute live fields
    current_price = await _get_current_price(holding.ticker, db)
    total_cost = holding.shares * holding.avg_buy_price
    current_value = holding.shares * current_price if current_price else None
    unrealised_pnl = (current_value - total_cost) if current_value is not None else None
    unrealised_pnl_pct = (
        (unrealised_pnl / total_cost * 100) if unrealised_pnl is not None and total_cost > 0 else None
    )

    return {
        "id": holding.id,
        "ticker": holding.ticker,
        "name": holding.stock.name if holding.stock else None,
        "shares": holding.shares,
        "avg_buy_price": holding.avg_buy_price,
        "buy_date": holding.buy_date,
        "notes": holding.notes,
        "current_price": current_price,
        "current_value": round(current_value, 2) if current_value else None,
        "total_cost": round(total_cost, 2),
        "unrealised_pnl": round(unrealised_pnl, 2) if unrealised_pnl is not None else None,
        "unrealised_pnl_pct": round(unrealised_pnl_pct, 2) if unrealised_pnl_pct is not None else None,
        "sector": holding.stock.sector if holding.stock else None,
        "country": holding.stock.country if holding.stock else None,
        "market_cap_category": holding.stock.market_cap_category if holding.stock else None,
    }


@router.delete("/holdings/{holding_id}")
async def delete_holding(
    holding_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a holding."""
    result = await db.execute(
        select(PortfolioHolding).where(PortfolioHolding.id == holding_id)
    )
    holding = result.scalar_one_or_none()

    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")

    holding.is_active = False
    await db.flush()
    return {"deleted": True}


@router.get("/stats", response_model=PortfolioStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get portfolio-level statistics."""
    result = await db.execute(
        select(PortfolioHolding)
        .options(joinedload(PortfolioHolding.stock))
        .where(PortfolioHolding.is_active == True)  # noqa: E712
    )
    holdings = result.scalars().unique().all()

    total_value = 0.0
    total_cost = 0.0
    beta_sum = 0.0
    beta_weight_sum = 0.0

    for h in holdings:
        current_price = await _get_current_price(h.ticker, db)
        cost = h.shares * h.avg_buy_price
        total_cost += cost

        if current_price:
            value = h.shares * current_price
            total_value += value
        else:
            value = cost
            total_value += cost

        # Fetch beta from yfinance
        try:
            info = await asyncio.to_thread(lambda t=h.ticker: yf.Ticker(t).info.get("beta"))
            if info and isinstance(info, (int, float)):
                beta_sum += info * value
                beta_weight_sum += value
        except Exception:
            pass

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
    portfolio_beta = (beta_sum / beta_weight_sum) if beta_weight_sum > 0 else None

    return {
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "beta": round(portfolio_beta, 4) if portfolio_beta is not None else None,
        "num_holdings": len(holdings),
        "quality_score_avg": None,  # TODO: compute from fundamentals
    }


@router.get("/allocations", response_model=PortfolioAllocations)
async def get_allocations(db: AsyncSession = Depends(get_db)):
    """Get portfolio allocation breakdowns by country, sector, market cap, holding."""
    result = await db.execute(
        select(PortfolioHolding)
        .options(joinedload(PortfolioHolding.stock))
        .where(PortfolioHolding.is_active == True)  # noqa: E712
    )
    holdings = result.scalars().unique().all()

    # Compute current value per holding
    holding_values: list[tuple[PortfolioHolding, float]] = []
    total = 0.0
    for h in holdings:
        current_price = await _get_current_price(h.ticker, db)
        value = h.shares * (current_price or h.avg_buy_price)
        holding_values.append((h, value))
        total += value

    if total == 0:
        return PortfolioAllocations(
            by_country=[], by_sector=[], by_market_cap=[], by_holding=[]
        )

    # Bucket by dimension
    def _bucket(key_fn) -> list[AllocationItem]:
        buckets: dict[str, float] = defaultdict(float)
        for h, val in holding_values:
            label = key_fn(h) or "Unknown"
            buckets[label] += val
        items = [
            AllocationItem(label=label, value=round(v, 2), percentage=round(v / total * 100, 1))
            for label, v in sorted(buckets.items(), key=lambda x: -x[1])
        ]
        return items

    return PortfolioAllocations(
        by_country=_bucket(lambda h: h.stock.country if h.stock else None),
        by_sector=_bucket(lambda h: h.stock.sector if h.stock else None),
        by_market_cap=_bucket(lambda h: h.stock.market_cap_category if h.stock else None),
        by_holding=_bucket(lambda h: h.ticker),
    )


@router.get("/performance", response_model=list[PortfolioPerformancePoint])
async def get_performance(db: AsyncSession = Depends(get_db)):
    """Get historical portfolio value vs S&P 500 benchmark."""
    result = await db.execute(
        select(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_date.asc())
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return []

    # Fetch SPY history
    try:
        spy_prices = await asyncio.to_thread(fetch_price_history, "SPY", "10y")
    except Exception:
        spy_prices = []

    spy_by_date: dict[str, float] = {}
    for p in spy_prices:
        spy_by_date[p["price_date"]] = p["close"]

    # Normalise SPY to portfolio starting value
    portfolio_start = snapshots[0].total_value
    spy_dates = sorted(spy_by_date.keys())
    spy_start = spy_by_date.get(spy_dates[0], 1.0) if spy_dates else 1.0

    points: list[dict] = []
    for snap in snapshots:
        date_str = snap.snapshot_date.isoformat()
        # Find nearest SPY date
        spy_val = spy_by_date.get(date_str)
        if spy_val is None:
            # Find nearest
            for d in spy_dates:
                if d <= date_str:
                    spy_val = spy_by_date[d]
                else:
                    break

        benchmark = (spy_val / spy_start * portfolio_start) if spy_val and spy_start else portfolio_start

        points.append(
            {
                "date": snap.snapshot_date,
                "portfolio_value": round(snap.total_value, 2),
                "benchmark_value": round(benchmark, 2),
            }
        )

    return points
