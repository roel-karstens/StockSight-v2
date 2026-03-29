"""
worker.py — Celery app with Beat schedule for background tasks.

Tasks:
  - refresh_all_fundamentals: nightly at 02:00 UTC
  - refresh_all_prices: hourly during market hours (14-21 UTC)
  - snapshot_portfolio: daily after market close (21:30 UTC)
"""

from __future__ import annotations

from datetime import date

from celery import Celery
from celery.schedules import crontab
from loguru import logger

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "portfolio_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
)

# ---------------------------------------------------------------------------
# Beat schedule
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    "refresh_all_fundamentals": {
        "task": "app.worker.refresh_all_fundamentals",
        "schedule": crontab(hour=2, minute=0),
    },
    "refresh_all_prices": {
        "task": "app.worker.refresh_all_prices",
        "schedule": crontab(minute=0, hour="14-21"),
    },
    "snapshot_portfolio": {
        "task": "app.worker.snapshot_portfolio",
        "schedule": crontab(hour=21, minute=30),
    },
}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@celery_app.task(name="app.worker.refresh_all_fundamentals")
def refresh_all_fundamentals():
    """Refresh fundamentals for all stocks in the database.

    Runs nightly. Reads all tickers from stocks table, re-fetches from yfinance,
    upserts updated rows.
    """
    # Import here to avoid circular imports + create sync DB session
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.models import Fundamental, Stock
    from app.services.data_fetcher import fetch_yfinance_financials

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)

    with Session(engine) as session:
        tickers = session.execute(select(Stock.ticker)).scalars().all()
        logger.info(f"refresh_all_fundamentals: processing {len(tickers)} tickers")

        for ticker in tickers:
            try:
                rows = fetch_yfinance_financials(ticker)
                for row in rows:
                    existing = session.execute(
                        select(Fundamental).where(
                            Fundamental.ticker == ticker,
                            Fundamental.fiscal_year == row.get("fiscal_year"),
                        )
                    ).scalar_one_or_none()

                    if existing:
                        for key, val in row.items():
                            if key != "fiscal_year" and val is not None:
                                setattr(existing, key, val)
                    else:
                        session.add(Fundamental(ticker=ticker, **row))

                session.commit()
                logger.info(f"refresh_all_fundamentals: updated {ticker}")
            except Exception as e:
                session.rollback()
                logger.error(f"refresh_all_fundamentals: failed for {ticker}: {e}")

    engine.dispose()


@celery_app.task(name="app.worker.refresh_all_prices")
def refresh_all_prices():
    """Refresh recent prices for all stocks.

    Runs hourly during market hours. Fetches last 5 days of prices,
    inserts only new rows.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.models import Price, Stock
    from app.services.data_fetcher import fetch_price_history

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)

    with Session(engine) as session:
        tickers = session.execute(select(Stock.ticker)).scalars().all()
        logger.info(f"refresh_all_prices: processing {len(tickers)} tickers")

        for ticker in tickers:
            try:
                prices = fetch_price_history(ticker, period="5d")
                inserted = 0
                for p in prices:
                    from datetime import date as date_type

                    price_date = date_type.fromisoformat(p["price_date"])
                    existing = session.execute(
                        select(Price).where(
                            Price.ticker == ticker,
                            Price.price_date == price_date,
                        )
                    ).scalar_one_or_none()

                    if not existing:
                        session.add(
                            Price(
                                ticker=ticker,
                                price_date=price_date,
                                open=p.get("open"),
                                high=p.get("high"),
                                low=p.get("low"),
                                close=p["close"],
                                adj_close=p.get("adj_close"),
                                volume=p.get("volume"),
                            )
                        )
                        inserted += 1

                session.commit()
                if inserted:
                    logger.info(f"refresh_all_prices: {ticker} +{inserted} rows")
            except Exception as e:
                session.rollback()
                logger.error(f"refresh_all_prices: failed for {ticker}: {e}")

    engine.dispose()


@celery_app.task(name="app.worker.snapshot_portfolio")
def snapshot_portfolio():
    """Create a daily portfolio snapshot.

    Runs after market close. Computes total value of all active holdings
    and saves to portfolio_snapshots.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.models import PortfolioHolding, PortfolioSnapshot, Price

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)

    today = date.today()

    with Session(engine) as session:
        # Check if snapshot already exists for today
        existing = session.execute(
            select(PortfolioSnapshot).where(PortfolioSnapshot.snapshot_date == today)
        ).scalar_one_or_none()

        if existing:
            logger.info(f"snapshot_portfolio: snapshot for {today} already exists, skipping")
            engine.dispose()
            return

        holdings = session.execute(
            select(PortfolioHolding).where(PortfolioHolding.is_active == True)  # noqa: E712
        ).scalars().all()

        if not holdings:
            logger.info("snapshot_portfolio: no active holdings, skipping")
            engine.dispose()
            return

        total_value = 0.0
        total_cost = 0.0
        holdings_data = []

        for h in holdings:
            cost = h.shares * h.avg_buy_price
            total_cost += cost

            # Get latest price
            latest_price = session.execute(
                select(Price)
                .where(Price.ticker == h.ticker)
                .order_by(Price.price_date.desc())
                .limit(1)
            ).scalar_one_or_none()

            price = latest_price.close if latest_price else h.avg_buy_price
            value = h.shares * price
            total_value += value

            holdings_data.append(
                {
                    "ticker": h.ticker,
                    "shares": h.shares,
                    "price": price,
                    "value": round(value, 2),
                }
            )

        snapshot = PortfolioSnapshot(
            snapshot_date=today,
            total_value=round(total_value, 2),
            total_cost=round(total_cost, 2),
            holdings_json={"holdings": holdings_data},
        )
        session.add(snapshot)
        session.commit()
        logger.info(
            f"snapshot_portfolio: created snapshot for {today} — "
            f"${total_value:,.2f} ({len(holdings)} holdings)"
        )

    engine.dispose()
