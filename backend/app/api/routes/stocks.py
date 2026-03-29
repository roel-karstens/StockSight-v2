"""
stocks.py — FastAPI routes for stock data endpoints.

All 7 stock endpoints per spec-backend-api.md:
  GET  /stocks/search?q={query}
  GET  /stocks/{ticker}
  GET  /stocks/{ticker}/fundamentals
  GET  /stocks/{ticker}/prices?period=10y
  GET  /stocks/compare?tickers=MSFT,AAPL
  POST /stocks/{ticker}/dcf
  GET  /stocks/{ticker}/reverse-dcf
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.cache import cache_get, cache_set
from app.db.session import get_db
from app.models.models import Fundamental, Price, Stock
from app.schemas.schemas import (
    DCFInputSchema,
    DCFOutputSchema,
    FundamentalOut,
    PriceHistoryResponse,
    PricePoint,
    QualityCriteria,
    ReverseDCFOutputSchema,
    StockFundamentalsResponse,
    StockOut,
    StockSearchResult,
)
from app.services.data_fetcher import (
    fetch_price_history,
    fetch_stock_info,
    fetch_yfinance_financials,
    merge_fundamentals,
    scrape_stock_analysis,
    scrape_stock_analysis_balance_sheet,
    scrape_stock_analysis_search,
)
from app.services.dcf import (
    DCFInput,
    calculate_dcf,
    calculate_reverse_dcf,
    compute_quality_criteria,
)

router = APIRouter(prefix="/stocks", tags=["stocks"])


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _get_or_create_stock(ticker: str, db: AsyncSession) -> Stock:
    """Look up stock by ticker; if not found, fetch from yfinance and create."""
    ticker = ticker.upper()
    result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = result.scalar_one_or_none()

    if stock is not None:
        return stock

    # Fetch from yfinance (run sync function in thread)
    info = await asyncio.to_thread(fetch_stock_info, ticker)

    stock = Stock(
        ticker=ticker,
        name=info.get("name"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        country=info.get("country"),
        exchange=info.get("exchange"),
        currency=info.get("currency"),
        market_cap=info.get("market_cap"),
        market_cap_category=info.get("market_cap_category"),
        description=info.get("description"),
        website=info.get("website"),
        last_updated=datetime.utcnow(),
    )
    db.add(stock)
    await db.flush()
    return stock


async def _seed_fundamentals(ticker: str, db: AsyncSession) -> None:
    """Fetch fundamentals from both sources, merge, and upsert into DB."""
    ticker = ticker.upper()

    # Fetch yfinance and stockanalysis data concurrently
    yf_task = asyncio.to_thread(fetch_yfinance_financials, ticker)
    sa_task = scrape_stock_analysis(ticker)
    yf_data, sa_data = await asyncio.gather(yf_task, sa_task, return_exceptions=True)

    if isinstance(yf_data, Exception):
        logger.warning(f"yfinance fetch failed for {ticker}: {yf_data}")
        yf_data = []
    if isinstance(sa_data, Exception):
        logger.warning(f"stockanalysis scrape failed for {ticker}: {sa_data}")
        sa_data = []

    # Fetch balance sheet for ROCE
    bs_data = await scrape_stock_analysis_balance_sheet(ticker)

    # Merge all sources
    merged = merge_fundamentals(yf_data, sa_data, bs_data)

    # Upsert each year into DB
    for row in merged:
        stmt = pg_insert(Fundamental).values(
            ticker=ticker,
            fiscal_year=row.get("fiscal_year"),
            roce=row.get("roce"),
            revenue_growth=row.get("revenue_growth"),
            fcf_growth=row.get("fcf_growth"),
            eps_growth=row.get("eps_growth"),
            lt_debt_to_fcf=row.get("lt_debt_to_fcf"),
            peg_ratio=row.get("peg_ratio"),
            revenue=row.get("revenue"),
            gross_profit=row.get("gross_profit"),
            operating_income=row.get("operating_income"),
            net_income=row.get("net_income"),
            ebitda=row.get("ebitda"),
            free_cash_flow=row.get("free_cash_flow"),
            capital_employed=row.get("capital_employed"),
            total_debt=row.get("total_debt"),
            long_term_debt=row.get("long_term_debt"),
            cash_and_equivalents=row.get("cash_and_equivalents"),
            shares_outstanding=row.get("shares_outstanding"),
            eps=row.get("eps"),
            dividend_per_share=row.get("dividend_per_share"),
        ).on_conflict_do_update(
            index_elements=["ticker", "fiscal_year"],
            set_={
                "roce": row.get("roce"),
                "revenue_growth": row.get("revenue_growth"),
                "fcf_growth": row.get("fcf_growth"),
                "eps_growth": row.get("eps_growth"),
                "lt_debt_to_fcf": row.get("lt_debt_to_fcf"),
                "peg_ratio": row.get("peg_ratio"),
                "revenue": row.get("revenue"),
                "gross_profit": row.get("gross_profit"),
                "operating_income": row.get("operating_income"),
                "net_income": row.get("net_income"),
                "ebitda": row.get("ebitda"),
                "free_cash_flow": row.get("free_cash_flow"),
                "capital_employed": row.get("capital_employed"),
                "total_debt": row.get("total_debt"),
                "long_term_debt": row.get("long_term_debt"),
                "cash_and_equivalents": row.get("cash_and_equivalents"),
                "shares_outstanding": row.get("shares_outstanding"),
                "eps": row.get("eps"),
                "dividend_per_share": row.get("dividend_per_share"),
            },
        )
        await db.execute(stmt)

    await db.flush()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/search", response_model=list[StockSearchResult])
async def search_stocks(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    """Search for stocks by ticker or name."""
    # Check cache
    cache_key = f"search:{q.lower()}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # Query DB first
    result = await db.execute(
        select(Stock)
        .where(Stock.ticker.ilike(f"{q}%") | Stock.name.ilike(f"%{q}%"))
        .limit(10)
    )
    db_stocks = result.scalars().all()

    results: list[dict] = []
    for stock in db_stocks:
        # Fetch quality score from fundamentals
        fund_result = await db.execute(
            select(Fundamental)
            .where(Fundamental.ticker == stock.ticker)
            .order_by(Fundamental.fiscal_year.asc())
        )
        fund_rows = fund_result.scalars().all()
        fund_dicts = [
            {
                "roce": f.roce,
                "revenue_growth": f.revenue_growth,
                "fcf_growth": f.fcf_growth,
                "eps_growth": f.eps_growth,
                "lt_debt_to_fcf": f.lt_debt_to_fcf,
                "peg_ratio": f.peg_ratio,
            }
            for f in fund_rows
        ]
        quality = compute_quality_criteria(fund_dicts, window=3) if fund_dicts else {"score": 0}

        results.append(
            {
                "ticker": stock.ticker,
                "name": stock.name,
                "sector": stock.sector,
                "country": stock.country,
                "market_cap_category": stock.market_cap_category,
                "quality_score": quality["score"],
            }
        )

    # If DB returns nothing, try stockanalysis search
    if not results:
        sa_results = await scrape_stock_analysis_search(q)
        results = [
            {
                "ticker": r["ticker"],
                "name": r["name"],
                "sector": None,
                "country": None,
                "market_cap_category": None,
                "quality_score": 0,
            }
            for r in sa_results
        ]

    await cache_set(cache_key, results, ttl=3600)
    return results


@router.get("/{ticker}", response_model=StockOut)
async def get_stock(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get stock metadata."""
    stock = await _get_or_create_stock(ticker, db)
    return stock


@router.get("/{ticker}/fundamentals", response_model=StockFundamentalsResponse)
async def get_fundamentals(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get 10-year fundamental data with quality scores."""
    ticker = ticker.upper()

    # Check cache
    cache_key = f"fundamentals:{ticker}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # Ensure stock exists
    stock = await _get_or_create_stock(ticker, db)

    # Query fundamentals
    result = await db.execute(
        select(Fundamental)
        .where(Fundamental.ticker == ticker)
        .order_by(Fundamental.fiscal_year.asc())
    )
    fund_rows = result.scalars().all()

    # If no fundamentals, seed them
    if not fund_rows:
        await _seed_fundamentals(ticker, db)
        result = await db.execute(
            select(Fundamental)
            .where(Fundamental.ticker == ticker)
            .order_by(Fundamental.fiscal_year.asc())
        )
        fund_rows = result.scalars().all()

    # Build response
    fund_dicts = [
        {
            "fiscal_year": f.fiscal_year,
            "roce": f.roce,
            "revenue_growth": f.revenue_growth,
            "fcf_growth": f.fcf_growth,
            "eps_growth": f.eps_growth,
            "lt_debt_to_fcf": f.lt_debt_to_fcf,
            "peg_ratio": f.peg_ratio,
            "revenue": f.revenue,
            "free_cash_flow": f.free_cash_flow,
            "net_income": f.net_income,
            "eps": f.eps,
            "pe_ratio": f.pe_ratio,
            "shares_outstanding": f.shares_outstanding,
            "long_term_debt": f.long_term_debt,
        }
        for f in fund_rows
    ]

    avg_3yr = compute_quality_criteria(fund_dicts, window=3)
    avg_10yr = compute_quality_criteria(fund_dicts, window=10)

    response = {
        "ticker": ticker,
        "name": stock.name,
        "fundamentals": fund_dicts,
        "avg_3yr": avg_3yr,
        "avg_10yr": avg_10yr,
    }

    await cache_set(cache_key, response, ttl=86400)
    return response


@router.get("/{ticker}/prices", response_model=PriceHistoryResponse)
async def get_prices(
    ticker: str,
    period: Literal["1y", "3y", "5y", "10y", "max"] = "10y",
    db: AsyncSession = Depends(get_db),
):
    """Get price history for a stock."""
    ticker = ticker.upper()

    # Check cache
    cache_key = f"prices:{ticker}:{period}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # Query DB
    result = await db.execute(
        select(Price)
        .where(Price.ticker == ticker)
        .order_by(Price.price_date.asc())
    )
    price_rows = result.scalars().all()

    # If no prices in DB, fetch and insert
    if not price_rows:
        await _get_or_create_stock(ticker, db)
        raw_prices = await asyncio.to_thread(fetch_price_history, ticker, period)
        for p in raw_prices:
            price_obj = Price(
                ticker=ticker,
                price_date=date.fromisoformat(p["price_date"]),
                open=p.get("open"),
                high=p.get("high"),
                low=p.get("low"),
                close=p["close"],
                adj_close=p.get("adj_close"),
                volume=p.get("volume"),
            )
            db.add(price_obj)
        await db.flush()

        # Re-query
        result = await db.execute(
            select(Price)
            .where(Price.ticker == ticker)
            .order_by(Price.price_date.asc())
        )
        price_rows = result.scalars().all()

    response = {
        "ticker": ticker,
        "prices": [
            {
                "date": p.price_date.isoformat(),
                "close": p.close,
                "adj_close": p.adj_close,
                "volume": p.volume,
            }
            for p in price_rows
        ],
    }

    await cache_set(cache_key, response, ttl=3600)
    return response


@router.get("/compare", response_model=dict)
async def compare_stocks(
    tickers: str = Query(..., description="Comma-separated tickers, max 5"),
    db: AsyncSession = Depends(get_db),
):
    """Compare fundamentals for multiple stocks."""
    ticker_list = [t.strip().upper() for t in tickers.split(",")][:5]
    result: dict = {}

    for ticker in ticker_list:
        try:
            fund_result = await db.execute(
                select(Fundamental)
                .where(Fundamental.ticker == ticker)
                .order_by(Fundamental.fiscal_year.asc())
            )
            fund_rows = fund_result.scalars().all()

            if not fund_rows:
                # Seed data
                await _get_or_create_stock(ticker, db)
                await _seed_fundamentals(ticker, db)
                fund_result = await db.execute(
                    select(Fundamental)
                    .where(Fundamental.ticker == ticker)
                    .order_by(Fundamental.fiscal_year.asc())
                )
                fund_rows = fund_result.scalars().all()

            fund_dicts = [
                {
                    "fiscal_year": f.fiscal_year,
                    "roce": f.roce,
                    "revenue_growth": f.revenue_growth,
                    "fcf_growth": f.fcf_growth,
                    "eps_growth": f.eps_growth,
                    "lt_debt_to_fcf": f.lt_debt_to_fcf,
                    "peg_ratio": f.peg_ratio,
                    "revenue": f.revenue,
                    "free_cash_flow": f.free_cash_flow,
                    "net_income": f.net_income,
                    "eps": f.eps,
                    "pe_ratio": f.pe_ratio,
                    "shares_outstanding": f.shares_outstanding,
                    "long_term_debt": f.long_term_debt,
                }
                for f in fund_rows
            ]

            result[ticker] = {
                "fundamentals": fund_dicts,
                "avg_3yr": compute_quality_criteria(fund_dicts, window=3),
                "avg_10yr": compute_quality_criteria(fund_dicts, window=10),
            }
        except Exception as e:
            logger.warning(f"compare: skipping {ticker}: {e}")
            continue

    return result


@router.post("/{ticker}/dcf", response_model=DCFOutputSchema)
async def compute_dcf(
    ticker: str,
    inputs: DCFInputSchema,
    db: AsyncSession = Depends(get_db),
):
    """Compute DCF intrinsic value with user-adjustable inputs."""
    ticker = ticker.upper()

    # Get latest fundamental
    result = await db.execute(
        select(Fundamental)
        .where(Fundamental.ticker == ticker)
        .order_by(Fundamental.fiscal_year.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    if latest is None or latest.free_cash_flow is None:
        raise HTTPException(status_code=404, detail=f"No FCF data for {ticker}")

    # Get latest price
    price_result = await db.execute(
        select(Price)
        .where(Price.ticker == ticker)
        .order_by(Price.price_date.desc())
        .limit(1)
    )
    latest_price = price_result.scalar_one_or_none()
    current_price = latest_price.close if latest_price else None

    dcf_inputs = DCFInput(
        wacc=inputs.wacc,
        terminal_growth=inputs.terminal_growth,
        fcf_growth_years_1_5=inputs.fcf_growth_years_1_5,
        fcf_growth_years_6_10=inputs.fcf_growth_years_6_10,
        years=inputs.years,
    )

    output = calculate_dcf(
        base_fcf=latest.free_cash_flow,
        shares_outstanding=latest.shares_outstanding or 1e9,
        current_price=current_price,
        inputs=dcf_inputs,
    )

    return output


@router.get("/{ticker}/reverse-dcf", response_model=ReverseDCFOutputSchema)
async def get_reverse_dcf(
    ticker: str,
    wacc: float = Query(0.10, ge=0.01, le=0.50),
    terminal_growth: float = Query(0.03, ge=0.00, le=0.10),
    db: AsyncSession = Depends(get_db),
):
    """Compute reverse DCF — implied growth rate from current market price."""
    ticker = ticker.upper()

    # Get latest fundamental
    result = await db.execute(
        select(Fundamental)
        .where(Fundamental.ticker == ticker)
        .order_by(Fundamental.fiscal_year.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    if latest is None or latest.free_cash_flow is None:
        raise HTTPException(status_code=404, detail=f"No FCF data for {ticker}")

    # Get latest price
    price_result = await db.execute(
        select(Price)
        .where(Price.ticker == ticker)
        .order_by(Price.price_date.desc())
        .limit(1)
    )
    latest_price = price_result.scalar_one_or_none()

    if latest_price is None:
        raise HTTPException(status_code=404, detail=f"No price data for {ticker}")

    output = calculate_reverse_dcf(
        current_price=latest_price.close,
        shares_outstanding=latest.shares_outstanding or 1e9,
        base_fcf=latest.free_cash_flow,
        wacc=wacc,
        terminal_growth=terminal_growth,
    )

    return output
