# spec-backend-services.md
# Backend Services Layer

> **Phase:** 1 — Extract & stabilise business logic  
> **Goal:** All data fetching, scraping, and calculations live in `app/services/`. No FastAPI routes yet. Each function is independently testable.  
> **Done when:** You can call every function directly from a Python shell and get correct results.

---

## Context

The existing Streamlit app mixes data fetching, calculations, and UI in the same files. This spec extracts all non-UI logic into clean, reusable service modules. FastAPI will call these services — it never fetches data itself.

---

## File: `app/services/data_fetcher.py`

### Responsibilities
- Fetch stock metadata and current price (yfinance)
- Fetch 10-year price history (yfinance)
- Fetch annual income/balance/cashflow statements (yfinance fallback)
- Scrape 10-year financials table from stockanalysis.com
- Scrape balance sheet from stockanalysis.com (for ROCE)
- Search stockanalysis.com for ticker suggestions

### Functions

#### `fetch_stock_info(ticker: str) -> dict`
- Uses `yf.Ticker(ticker).info`
- Returns: `ticker, name, sector, industry, country, exchange, currency, market_cap, description, website, current_price, beta, pe_ratio, peg_ratio`
- Derives `market_cap_category` from market_cap:
  - `>= 200B` → `mega`
  - `>= 10B`  → `large`
  - `>= 2B`   → `mid`
  - `>= 300M` → `small`
  - else      → `micro`
- On any exception: log warning, return `{"ticker": ticker.upper()}`

#### `fetch_price_history(ticker: str, period: str = "10y") -> list[dict]`
- Uses `yf.Ticker(ticker).history(period=period, auto_adjust=True)`
- Each row: `price_date (str YYYY-MM-DD), open, high, low, close, adj_close, volume (int)`
- Returns `[]` on error

#### `fetch_yfinance_financials(ticker: str) -> list[dict]`
- Reads `t.financials`, `t.balance_sheet`, `t.cashflow`
- One dict per fiscal year with: `fiscal_year (int), revenue, net_income, ebitda, free_cash_flow, long_term_debt, shares_outstanding, eps`
- After building rows, calls `_compute_growth_rates(rows)` in-place
- Sorts ascending by `fiscal_year`
- Returns `[]` on error

#### `async scrape_stock_analysis(ticker: str) -> list[dict]`
- URL: `https://stockanalysis.com/stocks/{ticker.lower()}/financials/`
- Uses `httpx.AsyncClient` with `HEADERS`, timeout from settings
- Awaits `asyncio.sleep(settings.REQUEST_DELAY)` before each request
- Parses first `<table>` with BeautifulSoup lxml
- Header row: year columns (first 4 chars parsed as int)
- Data rows: metric name in col 0, values in subsequent cols
- Calls `_parse_number()` on each cell value
- Calls `_map_stockanalysis_fields()` to rename columns to schema names
- Decorated with `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))`
- Returns `[]` on parse failure

#### `async scrape_stock_analysis_balance_sheet(ticker: str) -> list[dict]`
- URL: `https://stockanalysis.com/stocks/{ticker.lower()}/financials/balance-sheet/`
- Same parsing approach as above
- Returns raw field names (not remapped) — used for ROCE calculation

#### `async scrape_stock_analysis_search(query: str) -> list[dict]`
- URL: `https://stockanalysis.com/search/?q={query}`
- Finds all `<a href*='/stocks/'>` elements
- Extracts ticker from href path segment after `/stocks/`
- Returns up to 10 results: `[{ticker, name}]`
- Timeout: 10s, returns `[]` on error

### Private Helpers

#### `_parse_number(s: str) -> float | None`
- Strips commas, `%` signs
- Handles suffixes: `B` → ×1e9, `M` → ×1e6, `K` → ×1e3
- Returns `None` for `"-"`, `"—"`, `"N/A"`, empty string
- Returns `None` on `ValueError`

#### `_map_stockanalysis_fields(rows: list[dict]) -> list[dict]`
Field mapping:
```python
{
  "Revenue":                        "revenue",
  "Gross Profit":                   "gross_profit",
  "Operating Income":               "operating_income",
  "Net Income":                     "net_income",
  "EBITDA":                         "ebitda",
  "Free Cash Flow":                 "free_cash_flow",
  "EPS (Diluted)":                  "eps",
  "Shares Outstanding (Diluted)":   "shares_outstanding",
  "Dividends Per Share":            "dividend_per_share",
}
```

#### `_compute_growth_rates(rows: list[dict]) -> None`
- Mutates rows in-place
- For each of `revenue`, `free_cash_flow`, `eps`:
  - `growth_key = metric + "_growth"`
  - `rows[i][growth_key] = (curr - prev) / abs(prev)` when both non-None and prev != 0

#### `_safe_get(df, row_label, col) -> float | None`
- Safe pandas `.loc` access, returns `None` on KeyError/NaN

#### `_categorise_market_cap(market_cap: float | None) -> str | None`
- See thresholds above

### Constants
```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    "Accept-Language": "en-US,en;q=0.9",
}
```

---

## File: `app/services/dcf.py`

### Responsibilities
- Calculate DCF intrinsic value (2-stage model)
- Calculate reverse DCF implied growth rate
- Compute quality criteria pass/fail/score from fundamentals

### Functions

#### `calculate_dcf(base_fcf, shares_outstanding, current_price, inputs: DCFInput) -> DCFOutput`

**Model:**
- Stage 1 (years 1–5): grow FCF at `inputs.fcf_growth_years_1_5`
- Stage 2 (years 6–10): grow FCF at `inputs.fcf_growth_years_6_10`
- Each year: `fcf = fcf * (1 + growth)`, `pv = fcf / (1 + wacc) ** year`
- Terminal value: Gordon Growth Model
  - `terminal_fcf = final_fcf * (1 + terminal_growth)`
  - `terminal_value = terminal_fcf / (wacc - terminal_growth)`
  - `terminal_pv = terminal_value / (1 + wacc) ** years`
- `total_pv = sum(all yearly PVs) + terminal_pv`
- `intrinsic_value = total_pv / shares_outstanding`
- `margin_of_safety = (intrinsic_value - current_price) / current_price * 100`

**Returns `DCFOutput`:**
```python
intrinsic_value_per_share: float
current_price: float | None
margin_of_safety: float | None   # percent, positive = undervalued
projected_fcfs: list[dict]       # [{year, fcf, pv, growth_rate}]
terminal_value: float            # PV of terminal value
total_pv: float
```

#### `calculate_reverse_dcf(current_price, shares_outstanding, base_fcf, wacc, terminal_growth, years) -> ReverseDCFOutput`

**Model:**
- Target: `current_price * shares_outstanding` (market cap)
- Binary search over growth rate range `[-0.30, 1.00]`, 100 iterations
- Inner `dcf_value(growth_rate)` function: single-stage growth, same terminal value formula
- Convergence when `abs(dcf_value - target) < 1e4`
- Sensitivity table: growth rates `[-5%, 0%, 5%, 10%, 15%, 18%, 20%, 25%, 30%]`
  - Each entry: `{growth_rate, implied_price}`
  - Skip on ZeroDivisionError or OverflowError

**Returns `ReverseDCFOutput`:**
```python
implied_growth_rate: float
current_price: float
wacc: float
sensitivity: list[dict]   # [{growth_rate, implied_price}]
```

#### `compute_quality_criteria(fundamentals: list[dict], window: int = 10) -> dict`

- Takes last `window` years (sorted by `fiscal_year` desc, then slice)
- Computes average of each metric over window (ignoring None values)
- Thresholds:

| Metric | Threshold | Pass |
|---|---|---|
| `roce` | 10 | avg > 10 |
| `revenue_growth` | 0.10 | avg > 0.10 |
| `fcf_growth` | 0.10 | avg > 0.10 |
| `eps_growth` | 0.10 | avg > 0.10 |
| `lt_debt_to_fcf` | 4 | avg < 4 |
| `peg_ratio` | 2 | avg < 2 |

- Returns:
```python
{
  "roce_ok": bool,
  "revenue_growth_ok": bool,
  "fcf_growth_ok": bool,
  "eps_growth_ok": bool,
  "lt_debt_fcf_ok": bool,
  "peg_ok": bool,
  "score": int,   # count of True values, 0–6
}
```

#### `compute_roce(operating_income, total_assets, current_liabilities) -> float | None`
- `capital_employed = total_assets - current_liabilities`
- Returns `operating_income / capital_employed * 100`
- Returns `None` if any input is None or capital_employed is 0

#### `merge_fundamentals(yf_data: list[dict], sa_data: list[dict], bs_data: dict[int, dict]) -> list[dict]`
- Merges yfinance + stockanalysis data by fiscal year
- stockanalysis values overwrite yfinance where both exist and stockanalysis is non-None
- For each year, computes:
  - `roce` via `compute_roce` using balance sheet data
  - `lt_debt_to_fcf = long_term_debt / free_cash_flow` (None-safe)
  - `revenue_growth`, `fcf_growth`, `eps_growth` via `_compute_growth_rates`
- Returns sorted ascending by `fiscal_year`

---

## Verification Checklist

- [ ] `fetch_stock_info("MSFT")` returns dict with name, sector, country, market_cap
- [ ] `fetch_price_history("MSFT", "1y")` returns list of ~252 dicts with correct date format
- [ ] `fetch_yfinance_financials("MSFT")` returns list with `revenue_growth` populated from year 2
- [ ] `scrape_stock_analysis("MSFT")` returns list with `revenue` and `free_cash_flow` columns
- [ ] `scrape_stock_analysis_balance_sheet("MSFT")` returns rows with `Total Assets`
- [ ] `_parse_number("1.23B")` returns `1_230_000_000.0`
- [ ] `_parse_number("—")` returns `None`
- [ ] `calculate_dcf(87.6e9, 7.4e9, 421.50, DCFInput())` returns positive intrinsic value
- [ ] `calculate_reverse_dcf(421.50, 7.4e9, 87.6e9)` returns implied growth between 0 and 0.30
- [ ] `compute_quality_criteria(fundamentals)` returns score 0–6
- [ ] `merge_fundamentals(yf, sa, bs)` returns merged rows with `roce` populated
