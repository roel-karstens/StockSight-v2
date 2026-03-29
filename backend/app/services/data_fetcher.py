"""
data_fetcher.py — Data fetching service layer.

Combines yfinance (prices, metadata, 3-4yr financials) with
stockanalysis.com scraping (10yr financials, balance sheet, search).

All scraping functions are async (httpx). yfinance calls are synchronous
but wrapped for use in async contexts.

Ported from StockSight's data/fetcher.py, data/scraper.py, data/search.py.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Exchange mapping: StockAnalysis slug prefix → yfinance suffix
# (Ported from data/search.py EXCHANGE_MAP)
EXCHANGE_MAP: dict[str, str] = {
    "tsx": ".TO",
    "tsxv": ".V",
    "ams": ".AS",
    "sto": ".ST",
    "asx": ".AX",
    "fra": ".F",
    "lon": ".L",
    "epa": ".PA",
    "nze": ".NZ",
    "bit": ".MI",
    "hel": ".HE",
    "bvmf": ".SA",
    "swx": ".SW",
    "vie": ".VI",
    "otc": "",
    "snse": ".SN",
    "wse": ".WA",
    "bcba": ".BA",
    "ksc": ".KS",
    "koe": ".KS",
    "hkse": ".HK",
    "sse": ".SS",
    "szse": ".SZ",
    "tse": ".T",
    "nse": ".NS",
    "bse": ".BO",
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_number(s: str) -> float | None:
    """Parse a formatted financial value string to float.

    Handles: commas, %, B/M/K suffixes, dashes, parenthetical negatives.
    Returns None for missing or unparseable values.

    Ported from data/scraper.py _parse_value + spec additions for B/M/K.
    """
    if not s:
        return None
    s = s.strip()
    if s in ("-", "—", "–", "N/A", "n/a", ""):
        return None

    # Remove percentage sign
    s = s.replace("%", "")
    # Remove commas
    s = s.replace(",", "")

    # Handle parenthetical negatives: (123) → -123
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]

    # Handle suffixes: B, M, K
    multiplier = 1.0
    if s.endswith("B"):
        multiplier = 1e9
        s = s[:-1]
    elif s.endswith("M"):
        multiplier = 1e6
        s = s[:-1]
    elif s.endswith("K"):
        multiplier = 1e3
        s = s[:-1]

    try:
        return float(s) * multiplier
    except ValueError:
        return None


def _map_stockanalysis_fields(rows: list[dict]) -> list[dict]:
    """Rename raw stockanalysis.com column names to our schema names.

    Ported from spec-backend-services.md field mapping.
    """
    field_map = {
        "Revenue": "revenue",
        "Gross Profit": "gross_profit",
        "Operating Income": "operating_income",
        "Net Income": "net_income",
        "EBITDA": "ebitda",
        "Free Cash Flow": "free_cash_flow",
        "EPS (Diluted)": "eps",
        "Shares Outstanding (Diluted)": "shares_outstanding",
        "Dividends Per Share": "dividend_per_share",
    }
    mapped = []
    for row in rows:
        new_row: dict[str, Any] = {}
        for raw_key, value in row.items():
            schema_key = field_map.get(raw_key, raw_key)
            new_row[schema_key] = value
        mapped.append(new_row)
    return mapped


def _compute_growth_rates(rows: list[dict]) -> None:
    """Mutate rows in-place to add growth rate fields.

    For each of revenue, free_cash_flow, eps: compute YoY growth.
    Rows must be sorted ascending by fiscal_year.
    """
    metrics = ["revenue", "free_cash_flow", "eps"]
    for i in range(1, len(rows)):
        for metric in metrics:
            growth_key = f"{metric}_growth"
            curr = rows[i].get(metric)
            prev = rows[i - 1].get(metric)
            if curr is not None and prev is not None and prev != 0:
                rows[i][growth_key] = (curr - prev) / abs(prev)
            else:
                rows[i][growth_key] = None
    # First row has no previous — set growth to None
    if rows:
        for metric in metrics:
            rows[0][f"{metric}_growth"] = None


def _safe_get(df: pd.DataFrame, row_label: str, col: Any) -> float | None:
    """Safe pandas .loc access; returns None on KeyError or NaN."""
    try:
        val = df.loc[row_label, col]
        if pd.isna(val):
            return None
        return float(val)
    except (KeyError, TypeError, IndexError):
        return None


def _categorise_market_cap(market_cap: float | None) -> str | None:
    """Classify market cap into size bucket.

    Ported from data/allocation.py _classify_cap.
    """
    if market_cap is None:
        return None
    if market_cap >= 200_000_000_000:
        return "mega"
    if market_cap >= 10_000_000_000:
        return "large"
    if market_cap >= 2_000_000_000:
        return "mid"
    if market_cap >= 300_000_000:
        return "small"
    return "micro"


# ---------------------------------------------------------------------------
# yfinance-based functions (synchronous, run in thread pool for async use)
# ---------------------------------------------------------------------------


def fetch_stock_info(ticker: str) -> dict:
    """Fetch stock metadata and current price via yfinance.

    Returns a flat dict with: ticker, name, sector, industry, country,
    exchange, currency, market_cap, market_cap_category, description,
    website, current_price, beta, pe_ratio, peg_ratio.

    On any exception: logs warning, returns {"ticker": ticker.upper()}.

    Ported from data/fetcher.py fetch_yfinance (info portion).
    """
    try:
        t = yf.Ticker(ticker)
        info: dict = {}
        try:
            info = t.info or {}
        except Exception:
            pass

        # Fallback for market cap via fast_info
        if not info.get("marketCap"):
            try:
                fi = t.fast_info
                info["marketCap"] = int(getattr(fi, "market_cap", 0) or 0) or None
            except Exception:
                pass

        market_cap = info.get("marketCap")

        return {
            "ticker": ticker.upper(),
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "exchange": info.get("exchange"),
            "currency": info.get("currency"),
            "market_cap": market_cap,
            "market_cap_category": _categorise_market_cap(market_cap),
            "description": info.get("longBusinessSummary"),
            "website": info.get("website"),
            "current_price": (
                info.get("currentPrice") or info.get("regularMarketPrice")
            ),
            "beta": info.get("beta"),
            "pe_ratio": info.get("trailingPE"),
            "peg_ratio": info.get("pegRatio"),
        }
    except Exception as e:
        logger.warning(f"fetch_stock_info({ticker}) failed: {e}")
        return {"ticker": ticker.upper()}


def fetch_price_history(ticker: str, period: str = "10y") -> list[dict]:
    """Fetch historical OHLCV data via yfinance.

    Each row: {price_date, open, high, low, close, adj_close, volume}.
    Returns [] on error.

    Ported from data/fetcher.py fetch_yfinance (history portion).
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, auto_adjust=True)
        if hist is None or hist.empty:
            return []

        rows = []
        for dt, row in hist.iterrows():
            # Normalize timezone
            if hasattr(dt, "tz") and dt.tz is not None:
                dt = dt.tz_localize(None)
            rows.append(
                {
                    "price_date": dt.strftime("%Y-%m-%d"),
                    "open": float(row.get("Open", 0)) if pd.notna(row.get("Open")) else None,
                    "high": float(row.get("High", 0)) if pd.notna(row.get("High")) else None,
                    "low": float(row.get("Low", 0)) if pd.notna(row.get("Low")) else None,
                    "close": float(row["Close"]) if pd.notna(row.get("Close")) else 0.0,
                    "adj_close": float(row["Close"]) if pd.notna(row.get("Close")) else None,
                    "volume": int(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else 0,
                }
            )
        return rows
    except Exception as e:
        logger.warning(f"fetch_price_history({ticker}) failed: {e}")
        return []


def fetch_yfinance_financials(ticker: str) -> list[dict]:
    """Fetch annual financial statements from yfinance.

    Returns one dict per fiscal year with: fiscal_year, revenue, net_income,
    ebitda, free_cash_flow, long_term_debt, shares_outstanding, eps.
    Growth rates are computed in-place.

    Ported from data/fetcher.py fetch_yfinance + data/metrics.py helpers.
    """
    try:
        t = yf.Ticker(ticker)
        financials = t.financials
        balance_sheet = t.balance_sheet
        cashflow = t.cashflow

        if financials is None or financials.empty:
            return []

        # yfinance returns columns as dates, rows as line items → transpose
        inc = financials.T.sort_index()
        bal = balance_sheet.T.sort_index() if balance_sheet is not None and not balance_sheet.empty else pd.DataFrame()
        cf = cashflow.T.sort_index() if cashflow is not None and not cashflow.empty else pd.DataFrame()

        rows: list[dict] = []
        for dt in inc.index:
            year = dt.year if hasattr(dt, "year") else int(str(dt)[:4])

            def _get(df: pd.DataFrame, candidates: list[str]) -> float | None:
                for c in candidates:
                    if c in df.columns:
                        try:
                            val = df.loc[dt, c]
                            if pd.notna(val):
                                return float(val)
                        except (KeyError, TypeError):
                            pass
                return None

            row_data: dict[str, Any] = {
                "fiscal_year": year,
                "revenue": _get(inc, ["Total Revenue", "Revenue"]),
                "net_income": _get(inc, ["Net Income", "Net Income Common Stockholders"]),
                "ebitda": _get(inc, ["EBITDA"]),
                "eps": _get(inc, ["Diluted EPS", "Basic EPS"]),
                "shares_outstanding": _get(
                    inc,
                    ["Diluted Average Shares", "Basic Average Shares",
                     "Shares Outstanding", "Ordinary Shares Number"],
                ),
            }

            # Balance sheet items
            if not bal.empty:
                bal_dt = bal.index[bal.index.get_indexer([dt], method="nearest")[0]] if dt not in bal.index else dt
                row_data["long_term_debt"] = _get(
                    bal.loc[[bal_dt]] if bal_dt in bal.index else pd.DataFrame(),
                    ["Long Term Debt", "Long-Term Debt", "LongTermDebt"],
                )
                if row_data["long_term_debt"] is None and bal_dt in bal.index:
                    for c in ["Long Term Debt", "Long-Term Debt", "LongTermDebt"]:
                        if c in bal.columns:
                            try:
                                val = bal.loc[bal_dt, c]
                                if pd.notna(val):
                                    row_data["long_term_debt"] = float(val)
                                    break
                            except (KeyError, TypeError):
                                pass

            # Cash flow items
            if not cf.empty:
                cf_dt = cf.index[cf.index.get_indexer([dt], method="nearest")[0]] if dt not in cf.index else dt
                if cf_dt in cf.index:
                    for c in ["Free Cash Flow"]:
                        if c in cf.columns:
                            try:
                                val = cf.loc[cf_dt, c]
                                if pd.notna(val):
                                    row_data["free_cash_flow"] = float(val)
                                    break
                            except (KeyError, TypeError):
                                pass

            rows.append(row_data)

        # Compute growth rates in-place
        _compute_growth_rates(rows)

        # Sort ascending by fiscal_year
        rows.sort(key=lambda r: r["fiscal_year"])
        return rows

    except Exception as e:
        logger.warning(f"fetch_yfinance_financials({ticker}) failed: {e}")
        return []


# ---------------------------------------------------------------------------
# stockanalysis.com scraping (async with httpx)
# ---------------------------------------------------------------------------


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def scrape_stock_analysis(ticker: str) -> list[dict]:
    """Scrape 10-year income statement from stockanalysis.com.

    URL: https://stockanalysis.com/stocks/{ticker}/financials/
    Returns list of dicts, one per fiscal year, with schema-mapped field names.
    Returns [] on parse failure.

    Ported from data/scraper.py fetch_stockanalysis (income page).
    """
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/"

    try:
        await asyncio.sleep(settings.REQUEST_DELAY)
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=settings.REQUEST_TIMEOUT
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"scrape_stock_analysis({ticker}) request failed: {e}")
        return []

    try:
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table")
        if table is None:
            logger.warning(f"scrape_stock_analysis({ticker}): no table found")
            return []

        # Parse header row to get year columns
        thead = table.find("thead")
        headers: list[str] = []
        if thead:
            for cell in thead.find_all("th")[1:]:  # skip label column
                text = cell.get_text(strip=True)
                year_match = re.search(r"(\d{4})", text)
                if year_match:
                    headers.append(year_match.group(1))

        if not headers:
            return []

        # Parse data rows
        raw_data: dict[str, dict[str, float | None]] = {}
        tbody = table.find("tbody")
        data_rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for row in data_rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True)
            if not label:
                continue
            row_values: dict[str, float | None] = {}
            for j, cell in enumerate(cells[1:]):
                if j < len(headers):
                    row_values[headers[j]] = _parse_number(cell.get_text(strip=True))
            raw_data[label] = row_values

        # Build list of dicts, one per year
        year_list = sorted(headers, key=lambda y: int(y))
        result: list[dict] = []
        for year_str in year_list:
            year_int = int(year_str[:4])
            entry: dict[str, Any] = {"fiscal_year": year_int}
            for label, year_vals in raw_data.items():
                entry[label] = year_vals.get(year_str)
            result.append(entry)

        # Map SA field names to schema names
        result = _map_stockanalysis_fields(result)
        # Compute growth rates
        _compute_growth_rates(result)
        return result

    except Exception as e:
        logger.warning(f"scrape_stock_analysis({ticker}) parse failed: {e}")
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def scrape_stock_analysis_balance_sheet(ticker: str) -> list[dict]:
    """Scrape balance sheet from stockanalysis.com for ROCE calculation.

    URL: https://stockanalysis.com/stocks/{ticker}/financials/balance-sheet/
    Returns raw field names (not remapped) — used for ROCE calculation.

    Ported from data/scraper.py fetch_stockanalysis (balance page).
    """
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/balance-sheet/"

    try:
        await asyncio.sleep(settings.REQUEST_DELAY)
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=settings.REQUEST_TIMEOUT
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"scrape_stock_analysis_balance_sheet({ticker}) request failed: {e}")
        return []

    try:
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table")
        if table is None:
            return []

        thead = table.find("thead")
        headers: list[str] = []
        if thead:
            for cell in thead.find_all("th")[1:]:
                text = cell.get_text(strip=True)
                year_match = re.search(r"(\d{4})", text)
                if year_match:
                    headers.append(year_match.group(1))

        if not headers:
            return []

        raw_data: dict[str, dict[str, float | None]] = {}
        tbody = table.find("tbody")
        data_rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for row in data_rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True)
            if not label:
                continue
            row_values: dict[str, float | None] = {}
            for j, cell in enumerate(cells[1:]):
                if j < len(headers):
                    row_values[headers[j]] = _parse_number(cell.get_text(strip=True))
            raw_data[label] = row_values

        year_list = sorted(headers, key=lambda y: int(y))
        result: list[dict] = []
        for year_str in year_list:
            year_int = int(year_str[:4])
            entry: dict[str, Any] = {"fiscal_year": year_int}
            for label, year_vals in raw_data.items():
                entry[label] = year_vals.get(year_str)
            result.append(entry)

        return result

    except Exception as e:
        logger.warning(f"scrape_stock_analysis_balance_sheet({ticker}) parse failed: {e}")
        return []


async def scrape_stock_analysis_search(query: str) -> list[dict]:
    """Search stockanalysis.com for ticker suggestions.

    Uses the SA search API endpoint (JSON). Returns up to 10 results
    as [{ticker, name}].

    Ported from data/search.py _search_stockanalysis.
    """
    url = "https://stockanalysis.com/api/search"
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=10
        ) as client:
            resp = await client.get(url, params={"q": query})
            resp.raise_for_status()
            data = resp.json().get("data", [])
    except Exception as e:
        logger.warning(f"scrape_stock_analysis_search({query}) failed: {e}")
        return []

    results: list[dict] = []
    for item in data:
        slug = item.get("s", "")
        if not slug:
            continue
        # Filter: stocks only
        item_type = item.get("st", item.get("t", ""))
        if item_type != "s" and item.get("t") != "s":
            continue

        name = item.get("n", slug)
        ticker_str = slug.split("/")[-1] if "/" in slug else slug
        results.append({"ticker": ticker_str.upper(), "name": name})
        if len(results) >= 10:
            break

    return results


# ---------------------------------------------------------------------------
# Fundamental merging
# ---------------------------------------------------------------------------


def merge_fundamentals(
    yf_data: list[dict],
    sa_data: list[dict],
    bs_data: list[dict],
) -> list[dict]:
    """Merge yfinance + stockanalysis income + balance sheet into unified rows.

    Priority: SA data fills the 10-year range; yfinance fills gaps.
    ROCE is computed from balance sheet data (Total Assets - Current Liabilities).
    LT Debt / FCF is computed here.
    PEG ratio is taken from yfinance info if available.

    Returns list of dicts sorted by fiscal_year ascending.
    """
    # Index by fiscal_year for quick lookup
    yf_by_year: dict[int, dict] = {r["fiscal_year"]: r for r in yf_data}
    bs_by_year: dict[int, dict] = {r["fiscal_year"]: r for r in bs_data}

    # Start with SA data as base, fill from yfinance where SA is missing
    merged: dict[int, dict] = {}

    # First add all SA rows
    for row in sa_data:
        fy = row["fiscal_year"]
        merged[fy] = dict(row)

    # Fill gaps from yfinance
    for fy, yf_row in yf_by_year.items():
        if fy not in merged:
            merged[fy] = dict(yf_row)
        else:
            # Fill None fields from yfinance
            for key, val in yf_row.items():
                if merged[fy].get(key) is None and val is not None:
                    merged[fy][key] = val

    # Compute ROCE from balance sheet data
    for fy, row in merged.items():
        bs_row = bs_by_year.get(fy, {})
        operating_income = row.get("operating_income")
        total_assets = bs_row.get("Total Assets")
        current_liabilities = bs_row.get("Current Liabilities")

        if (
            operating_income is not None
            and total_assets is not None
            and current_liabilities is not None
        ):
            capital_employed = total_assets - current_liabilities
            if capital_employed > 0:
                row["roce"] = (operating_income / capital_employed) * 100
            else:
                row["roce"] = None
        else:
            row.setdefault("roce", None)

        # LT Debt / FCF
        lt_debt = (
            row.get("long_term_debt")
            or bs_row.get("Long-Term Debt")
            or bs_row.get("Long Term Debt")
        )
        fcf = row.get("free_cash_flow")
        if lt_debt is not None and fcf is not None and fcf != 0:
            row["lt_debt_to_fcf"] = lt_debt / fcf
        else:
            row.setdefault("lt_debt_to_fcf", None)

        # Ensure growth fields exist
        row.setdefault("revenue_growth", None)
        row.setdefault("fcf_growth", None)
        row.setdefault("eps_growth", None)
        row.setdefault("peg_ratio", None)

        # Store balance sheet items
        row["total_debt"] = bs_row.get("Total Debt") or lt_debt
        row["long_term_debt"] = lt_debt
        row["cash_and_equivalents"] = (
            bs_row.get("Cash & Short-Term Investments")
            or bs_row.get("Cash & Equivalents")
        )
        row["capital_employed"] = (
            (total_assets - current_liabilities)
            if total_assets is not None and current_liabilities is not None
            else None
        )

    # Sort ascending by fiscal_year
    result = sorted(merged.values(), key=lambda r: r["fiscal_year"])

    # Recompute growth rates across the full merged dataset
    _compute_growth_rates(result)

    return result
