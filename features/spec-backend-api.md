# spec-backend-api.md
# Backend API Layer

> **Phase:** 2 — FastAPI routes, schemas, caching  
> **Depends on:** `spec-backend-services.md` complete and verified  
> **Goal:** Every endpoint returns correct data, documented at `/docs`, with Redis caching working.  
> **Done when:** You can hit every endpoint from the browser or curl and get correct responses.

---

## Context

Services are already extracted. This spec adds the HTTP layer on top: Pydantic schemas, FastAPI routes, Redis caching, and the main app entrypoint. No frontend yet — verify everything via Swagger UI at `http://localhost:8000/docs`.

---

## File: `app/schemas/schemas.py`

### Stock Schemas

```python
class StockBase(BaseModel):
    ticker: str
    name: str | None
    sector: str | None
    industry: str | None
    country: str | None
    exchange: str | None
    currency: str | None
    market_cap: float | None
    market_cap_category: str | None   # mega/large/mid/small/micro

class StockOut(StockBase):
    id: int
    description: str | None
    website: str | None
    last_updated: datetime | None
    model_config = {"from_attributes": True}

class StockSearchResult(BaseModel):
    ticker: str
    name: str | None
    sector: str | None
    country: str | None
    market_cap_category: str | None
    quality_score: int              # 0–6, from latest 3yr avg
```

### Fundamental Schemas

```python
class FundamentalOut(BaseModel):
    fiscal_year: int
    roce: float | None
    revenue_growth: float | None    # decimal, e.g. 0.148
    fcf_growth: float | None
    eps_growth: float | None
    lt_debt_to_fcf: float | None
    peg_ratio: float | None
    revenue: float | None
    free_cash_flow: float | None
    net_income: float | None
    eps: float | None
    pe_ratio: float | None
    shares_outstanding: float | None
    long_term_debt: float | None
    model_config = {"from_attributes": True}

class QualityCriteria(BaseModel):
    roce_ok: bool
    revenue_growth_ok: bool
    fcf_growth_ok: bool
    eps_growth_ok: bool
    lt_debt_fcf_ok: bool
    peg_ok: bool
    score: int                      # 0–6

class StockFundamentalsResponse(BaseModel):
    ticker: str
    name: str | None
    fundamentals: list[FundamentalOut]
    avg_3yr: QualityCriteria
    avg_10yr: QualityCriteria
```

### Price Schemas

```python
class PricePoint(BaseModel):
    date: date
    close: float
    adj_close: float | None
    volume: int | None

class PriceHistoryResponse(BaseModel):
    ticker: str
    prices: list[PricePoint]
```

### DCF Schemas

```python
class DCFInput(BaseModel):
    wacc: float                   = Field(0.10, ge=0.01, le=0.50)
    terminal_growth: float        = Field(0.03, ge=0.00, le=0.10)
    fcf_growth_years_1_5: float   = Field(0.15, ge=-0.50, le=1.00)
    fcf_growth_years_6_10: float  = Field(0.08, ge=-0.50, le=1.00)
    years: int                    = Field(10, ge=5, le=20)

class DCFOutput(BaseModel):
    intrinsic_value_per_share: float
    current_price: float | None
    margin_of_safety: float | None   # percent
    projected_fcfs: list[dict]       # [{year, fcf, pv, growth_rate}]
    terminal_value: float
    total_pv: float

class ReverseDCFOutput(BaseModel):
    implied_growth_rate: float
    current_price: float
    wacc: float
    sensitivity: list[dict]          # [{growth_rate, implied_price}]
```

### Portfolio Schemas

```python
class HoldingCreate(BaseModel):
    ticker: str
    shares: float     = Field(gt=0)
    avg_buy_price: float = Field(gt=0)
    buy_date: date
    notes: str | None = None

class HoldingUpdate(BaseModel):
    shares: float | None        = Field(None, gt=0)
    avg_buy_price: float | None = Field(None, gt=0)
    buy_date: date | None       = None
    notes: str | None           = None

class HoldingOut(BaseModel):
    id: int
    ticker: str
    name: str | None
    shares: float
    avg_buy_price: float
    buy_date: date
    notes: str | None
    current_price: float | None
    current_value: float | None
    total_cost: float | None
    unrealised_pnl: float | None
    unrealised_pnl_pct: float | None
    sector: str | None
    country: str | None
    market_cap_category: str | None
    model_config = {"from_attributes": True}

class AllocationItem(BaseModel):
    label: str
    value: float        # USD
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
    beta: float | None
    num_holdings: int
    quality_score_avg: float | None
```

---

## File: `app/db/cache.py`

### Functions

#### `async get_redis() -> aioredis.Redis`
- Singleton: creates `aioredis.from_url(settings.REDIS_URL, decode_responses=True)` once
- Returns cached client on subsequent calls

#### `async cache_get(key: str) -> dict | list | None`
- `await redis.get(key)` → `json.loads(data)` if data else `None`
- Logs warning on exception, returns `None` (never raises)

#### `async cache_set(key: str, value: dict | list, ttl: int = 3600) -> None`
- `await redis.setex(key, ttl, json.dumps(value, default=str))`
- Logs warning on exception, never raises

#### `async cache_delete(key: str) -> None`
- `await redis.delete(key)`
- Logs warning on exception, never raises

### Cache Key Convention
```
fundamentals:{ticker}           TTL: 86400  (24h)
prices:{ticker}:{period}        TTL: 3600   (1h)
stock_info:{ticker}             TTL: 86400  (24h)
search:{query}                  TTL: 3600   (1h)
```

---

## File: `app/api/routes/stocks.py`

### Router Setup
```python
router = APIRouter(prefix="/stocks", tags=["stocks"])
```

### Private Helper: `_get_or_create_stock(ticker, db)`
- Queries `Stock` table by ticker
- If not found: calls `fetch_stock_info(ticker)`, creates `Stock` row, flushes
- Returns `Stock` ORM object

### Private Helper: `_seed_fundamentals(ticker, db)`
- Calls `fetch_yfinance_financials(ticker)` and `scrape_stock_analysis(ticker)` concurrently (`asyncio.gather`)
- Calls `scrape_stock_analysis_balance_sheet(ticker)`
- Calls `merge_fundamentals(yf_data, sa_data, bs_data)` from `dcf.py`
- Upserts each year into `Fundamental` table (INSERT ... ON CONFLICT DO UPDATE)
- Logs any scraping errors, continues with partial data

---

### `GET /stocks/search?q={query}`
**Response:** `list[StockSearchResult]`

Logic:
1. Check cache key `search:{query}`; return if hit
2. Query DB: `ticker ILIKE '{q}%' OR name ILIKE '%{q}%'` LIMIT 10
3. For each DB result: fetch latest 3yr fundamentals, call `compute_quality_criteria(window=3)`, attach score
4. If DB returns 0 results: call `scrape_stock_analysis_search(query)`, return with `quality_score=0`
5. Cache result for 1h

---

### `GET /stocks/{ticker}`
**Response:** `StockOut`

Logic:
1. `await _get_or_create_stock(ticker, db)`
2. Return stock

---

### `GET /stocks/{ticker}/fundamentals`
**Response:** `StockFundamentalsResponse`

Logic:
1. Check cache key `fundamentals:{ticker}`; deserialise and return if hit
2. `await _get_or_create_stock(ticker, db)`
3. Query all `Fundamental` rows for ticker, order by `fiscal_year ASC`
4. If empty: call `await _seed_fundamentals(ticker, db)`; re-query
5. Build `fund_dicts` list from ORM rows
6. Compute `avg_3yr = compute_quality_criteria(fund_dicts, window=3)`
7. Compute `avg_10yr = compute_quality_criteria(fund_dicts, window=10)`
8. Build `StockFundamentalsResponse`, cache for 24h, return

---

### `GET /stocks/{ticker}/prices?period=10y`
**Response:** `PriceHistoryResponse`

**Query param:** `period` — one of `1y | 3y | 5y | 10y | max`, default `10y`

Logic:
1. Check cache key `prices:{ticker}:{period}`; return if hit
2. Query `Price` rows for ticker ordered by `price_date ASC`
3. If empty: call `fetch_price_history(ticker, period)`, bulk-insert, re-query
4. Build response, cache for 1h, return

---

### `GET /stocks/compare?tickers=MSFT,AAPL`
**Response:** `dict[str, dict]`  (ticker → fundamentals + quality)

Logic:
1. Split tickers on comma, strip, uppercase, limit to 5
2. For each ticker: query `Fundamental` rows (same as fundamentals endpoint, skip cache check)
3. Return `{ ticker: { fundamentals: [...], avg_3yr: {...}, avg_10yr: {...} } }`
4. Silently skip tickers with errors

---

### `POST /stocks/{ticker}/dcf`
**Body:** `DCFInput`  
**Response:** `DCFOutput`

Logic:
1. Query latest `Fundamental` row for ticker — 404 if none or no `free_cash_flow`
2. Query latest `Price` row for ticker — `current_price = None` if not found
3. Call `calculate_dcf(latest.free_cash_flow, latest.shares_outstanding or 1e9, current_price, inputs)`
4. Return result (no caching — user inputs vary)

---

### `GET /stocks/{ticker}/reverse-dcf?wacc=0.10&terminal_growth=0.03`
**Response:** `ReverseDCFOutput`

Logic:
1. Query latest `Fundamental` — 404 if no `free_cash_flow`
2. Query latest `Price` — 404 if no price
3. Call `calculate_reverse_dcf(price.close, latest.shares_outstanding or 1e9, latest.free_cash_flow, wacc, terminal_growth)`
4. Return result

---

## File: `app/api/routes/portfolio.py`

### Router Setup
```python
router = APIRouter(prefix="/portfolio", tags=["portfolio"])
```

### Private Helper: `_get_current_price(ticker, db) -> float | None`
- Queries latest `Price` row for ticker
- Returns `close` or `None`

---

### `GET /portfolio/holdings`
**Response:** `list[HoldingOut]`

Logic:
1. Join `PortfolioHolding` + `Stock` where `is_active = True`, order by `buy_date DESC`
2. For each row:
   - `current_price = await _get_current_price(ticker, db)`
   - `total_cost = shares * avg_buy_price`
   - `current_value = shares * current_price` (None if no price)
   - `unrealised_pnl = current_value - total_cost` (None if no price)
   - `unrealised_pnl_pct = unrealised_pnl / total_cost * 100` (None if no price)
3. Return list of `HoldingOut`

---

### `POST /portfolio/holdings`
**Body:** `HoldingCreate`  
**Response:** `HoldingOut`

Logic:
1. Uppercase ticker
2. `await _get_or_create_stock(ticker, db)` — seeds stock if new
3. Create `PortfolioHolding` row, flush
4. Compute live fields, return `HoldingOut`

---

### `PUT /portfolio/holdings/{holding_id}`
**Body:** `HoldingUpdate`  
**Response:** `HoldingOut`

Logic:
1. Fetch holding — 404 if not found
2. Update only non-None fields from payload
3. Flush, recompute live fields, return `HoldingOut`

---

### `DELETE /portfolio/holdings/{holding_id}`
**Response:** `{"deleted": True}`

Logic:
1. Fetch holding — 404 if not found
2. Set `is_active = False` (soft delete)

---

### `GET /portfolio/stats`
**Response:** `PortfolioStats`

Logic:
1. Fetch all active holdings with joined Stock
2. For each:
   - `current_price = await _get_current_price(ticker, db)`
   - Accumulate `total_value`, `total_cost`
   - Collect `(beta, position_value)` pairs from `yf.Ticker(ticker).info.get("beta")`
3. `portfolio_beta = Σ(beta × position_value) / Σ(position_value)`
4. Return `PortfolioStats`

---

### `GET /portfolio/allocations`
**Response:** `PortfolioAllocations`

Logic:
1. Fetch all active holdings with joined Stock
2. For each: compute current value (`price × shares`, fallback to `avg_buy_price × shares`)
3. Bucket values by `country`, `sector`, `market_cap_category`, and holding name
4. Compute percentages; sort each bucket by value descending
5. Return `PortfolioAllocations`

---

### `GET /portfolio/performance`
**Response:** `list[PortfolioPerformancePoint]`

Logic:
1. Query all `PortfolioSnapshot` rows ordered by `snapshot_date ASC`
2. If no snapshots: return `[]`
3. Fetch SPY price history via `yf.Ticker("SPY").history(period="10y")`
4. Normalise SPY to portfolio starting value: `spy_normalised = spy_price / spy_start * portfolio_start`
5. For each snapshot: match nearest SPY date, build `PortfolioPerformancePoint`
6. Return list

---

## File: `app/main.py`

```python
@asynccontextmanager
async def lifespan(app):
    # Create all tables (for dev; use Alembic in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="Alphavault API", version="0.1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(stocks.router,    prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## Verification Checklist

- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `GET /api/v1/stocks/search?q=MSFT` returns list with quality_score
- [ ] `GET /api/v1/stocks/MSFT` returns name, sector, country
- [ ] `GET /api/v1/stocks/MSFT/fundamentals` returns 10 years of data with `avg_3yr` and `avg_10yr`
- [ ] `GET /api/v1/stocks/MSFT/fundamentals` second call is faster (cache hit)
- [ ] `GET /api/v1/stocks/MSFT/prices?period=5y` returns ~1260 price points
- [ ] `GET /api/v1/stocks/compare?tickers=MSFT,AAPL` returns both tickers
- [ ] `POST /api/v1/stocks/MSFT/dcf` with default body returns `intrinsic_value_per_share > 0`
- [ ] `GET /api/v1/stocks/MSFT/reverse-dcf` returns `implied_growth_rate` between 0 and 0.5
- [ ] `POST /api/v1/portfolio/holdings` creates holding, returns `HoldingOut`
- [ ] `GET /api/v1/portfolio/holdings` returns holding with `unrealised_pnl`
- [ ] `GET /api/v1/portfolio/stats` returns `total_value`, `beta`
- [ ] `GET /api/v1/portfolio/allocations` returns 4 breakdowns, percentages sum to ~100
- [ ] `DELETE /api/v1/portfolio/holdings/{id}` soft-deletes (holding no longer in GET list)
- [ ] All endpoints appear correctly in Swagger UI at `/docs`
- [ ] 404 returned for unknown ticker on DCF endpoints
