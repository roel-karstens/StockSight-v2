# spec-design-brief.md
# Alphavault — Master Design Brief

> **Document type:** Top-level project brief  
> **Purpose:** Bridge the existing StockSight Streamlit app to the full Alphavault React web app. Read this first. Every sub-spec derives from this document.  
> **Audience:** Anyone building, reviewing, or extending this project.

---

## 1. What Exists Today — StockSight

The existing app is called **StockSight**, hosted at `github.com/roel-karstens/stocksight`.

### What it does
A lightweight Streamlit dashboard. You type a ticker, click Add, and see a colour-coded table of 7 financial health metrics for up to 5 stocks side by side.

### Current metrics tracked

| Metric | Green threshold | Red threshold |
|---|---|---|
| Gross Margin | ≥ 50% | < 20% |
| PEG Ratio | ≤ 2.0 | > 3.0 |
| Revenue Growth | > 10% | < 0% |
| ROCE | ≥ 15% | < 5% |
| FCF Growth | > 10% | < 0% |
| LT Debt / FCF | < 4.0× | > 5.0× |
| DCF Margin of Safety | ≥ +20% | < −20% |

### Current data source
Yahoo Finance exclusively, via `yfinance`. No API key required. Provides 3–4 years of annual statements.

### Current architecture
```
StockSight/
├── app.py              # Streamlit entry point — UI + wiring
├── data/
│   ├── fetcher.py      # yfinance calls + st.cache_data (1hr TTL)
│   └── metrics.py      # All 7 metric calculations
├── ui/
│   ├── charts.py       # Plotly chart builders
│   └── indicators.py   # Threshold config + green/amber/red logic
└── requirements.txt
```

### What it does well
- Very fast to use — one input, instant comparison table
- Clean metric definitions with clear thresholds
- DCF model already implemented (2-stage, 10yr, 10% WACC, 3% terminal)
- Plotly charts with threshold reference lines
- No auth, no setup — runs locally with one command

### What it lacks
- Only 3–4 years of data (yfinance limitation) — quality investing needs 10 years
- No portfolio management — can't save holdings, track P&L, or see performance
- No intrinsic value chart — only shows margin of safety as a number
- No reverse DCF
- No allocation breakdowns (country, sector, cap size)
- No portfolio beta
- No persistent data — every session starts fresh
- Streamlit UI limits: no smooth scroll, no animations, no custom layout control
- No background data refresh — re-fetches on every session

---

## 2. What We Are Building — Alphavault

**Alphavault** is a full-stack web application that replaces StockSight with a production-grade quality investing dashboard. Same investment philosophy, entirely new architecture and user experience.

### The core idea
> A single, continuously scrollable page that takes you from "I want to research a stock" all the way to "I understand my portfolio's health" — without ever changing page.

### Investment philosophy (unchanged from StockSight)
Quality investing: own companies that compound value over long periods by maintaining high returns on capital, consistent growth, and conservative debt.

**Quality criteria (10yr and 3yr averages):**

| Metric | Threshold | Direction |
|---|---|---|
| ROCE | > 10% | Above |
| Revenue Growth | > 10% | Above |
| FCF Growth | > 10% | Above |
| EPS Growth | > 10% | Above |
| LT Debt / FCF | < 4× | Below |
| PEG Ratio | < 2 | Below |

A stock scores 0–6 based on how many criteria it meets. 6/6 = excellent. Below 4/6 = watch carefully.

---

## 3. The User Journey

The app is a **single scrollable page** with 6 sections. The user flows through them naturally, top to bottom. A fixed sidebar shows where they are and lets them jump to any section.

```
┌─────────────────────────────────────────────────────────┐
│  ① SEARCH          "Find a stock"                       │
│     ↓ user types ticker, sees quality badge + sparkline │
│                                                         │
│  ② QUALITY         "Is it a quality company?"           │
│     ↓ radar chart + 6 criteria + 10yr trend charts      │
│                                                         │
│  ③ VALUATION       "Is it priced right?"                │
│     ↓ DCF intrinsic value + reverse DCF heatmap         │
│                                                         │
│  ④ COMPARE         "How does it stack up?"              │
│     ↓ overlay charts + scorecard table vs 4 other stocks│
│                                                         │
│  ⑤ PORTFOLIO       "What do I own?"                     │
│     ↓ holdings table + allocation donuts + performance  │
│                                                         │
│  ⑥ ALERTS          "Is my portfolio still healthy?"     │
│     ↓ auto-generated health cards from portfolio data   │
└─────────────────────────────────────────────────────────┘
```

The first four sections (Search → Quality → Valuation → Compare) are **stock research tools**. The last two (Portfolio → Alerts) are **portfolio management tools**. The sidebar has a visual separator between these two groups.

---

## 4. What Is New vs StockSight

| Capability | StockSight | Alphavault |
|---|---|---|
| Years of data | 3–4 (yfinance only) | 10 (yfinance + stockanalysis.com scrape) |
| Data persistence | None (session only) | PostgreSQL — survives restarts |
| Background refresh | None | Celery Beat — nightly fundamentals, hourly prices |
| Caching | Streamlit `st.cache_data` 1hr | Redis with configurable TTL per data type |
| Portfolio tracking | None | Full CRUD holdings, daily value snapshots |
| Performance chart | None | 10yr portfolio vs S&P 500 benchmark |
| Allocation charts | None | Country / sector / market cap donuts |
| Portfolio beta | None | Weighted avg beta across holdings |
| Quality alerts | None | Auto-generated from portfolio data |
| DCF | Margin of safety number only | Full waterfall chart + adjustable inputs |
| Reverse DCF | None | Implied growth rate + sensitivity heatmap |
| Compare | Side-by-side metric table | Overlay line charts + scorecard |
| Radar chart | None | 6-axis quality radar per stock |
| Metric history | None | 10yr trend chart per metric |
| UI | Streamlit (limited layout) | React — custom scroll, animations, charts |
| Data sources | yfinance only | yfinance + stockanalysis.com |

---

## 5. What To Preserve From StockSight

These things are already working correctly in StockSight and must be carried over without regression:

### 5.1 Metric calculations (`data/metrics.py`)
The 7 metric calculations are the core of the app. They must be extracted verbatim or equivalently into `app/services/dcf.py` and `app/services/data_fetcher.py`. Do not rewrite the logic from scratch — derive from what exists.

Specifically preserve:
- ROCE calculation method
- LT Debt / FCF ratio method
- DCF model parameters: 2-stage, 10yr projection, 10% WACC, 3% terminal growth
- Margin of safety formula
- The green/amber/red threshold values (now in `lib/quality.js` on the frontend)

### 5.2 Data fetching patterns (`data/fetcher.py`)
- yfinance income statement, balance sheet, and cashflow fetching patterns
- The 1hr cache TTL — preserved in Redis
- Graceful handling of missing data (some tickers have gaps)

### 5.3 Threshold config (`ui/indicators.py`)
The threshold values defined here become the `CRITERIA` array in `lib/quality.js`. The pass/warn/fail logic is the same, just extended with a 20% warn margin on either side of each threshold.

### 5.4 Chart concepts (`ui/charts.py`)
- Dashed threshold reference lines on every metric chart
- Plotly → Recharts (same concept, new library)
- Colour coding consistent with existing green/red semantics (now teal/amber/red)

---

## 6. Migration Strategy

### The golden rule
**The Streamlit app keeps running while the new app is being built.** Do not break StockSight. The new backend is built in parallel. StockSight is only decommissioned in the final phase when all features are verified.

### Four phases

```
Phase 1 — Extract & Stabilise Backend Services
  Goal:    Clean Python service functions, independently testable
  Input:   data/fetcher.py + data/metrics.py from StockSight
  Output:  app/services/data_fetcher.py + app/services/dcf.py
  Risk:    Low — pure Python, no UI involved
  Verify:  Call each function from Python shell, check outputs

Phase 2 — API + Infrastructure
  Goal:    FastAPI routes + Docker + DB + Redis + Celery running
  Input:   Phase 1 services
  Output:  All endpoints responding correctly at /docs
  Risk:    Medium — new infrastructure
  Verify:  Swagger UI shows all endpoints returning real data

Phase 3 — React Frontend (section by section)
  Goal:    One working section per sprint, never a half-built UI
  Input:   Phase 2 API
  Output:  Each section spec executed and verified in order
  Risk:    Low per section, isolated failures
  Verify:  Each section's checklist before moving to next

Phase 4 — Decommission Streamlit
  Goal:    Remove StockSight once Alphavault covers all features
  Input:   Completed Alphavault
  Output:  StockSight removed from docker-compose.yml
  Risk:    Low — final cleanup only
  Verify:  Feature parity checklist (see Section 9)
```

### Sub-spec execution order

```
spec-backend-services   →   spec-backend-infra
                        ↓
                    spec-backend-api
                        ↓
                spec-frontend-layout
                        ↓
              spec-section-search
                        ↓
              spec-section-quality
                        ↓
            spec-section-valuation
                        ↓
             spec-section-compare
                        ↓
            spec-section-portfolio
                        ↓
              spec-section-alerts
```

`spec-backend-infra` and `spec-backend-services` can be worked on in parallel. All other specs are strictly sequential.

---

## 7. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     React Frontend                       │
│  Vite · TailwindCSS · Recharts · Zustand · TanStack Q   │
│  Single scroll page · 6 sections · Fixed sidebar        │
└───────────────────┬─────────────────────────────────────┘
                    │ HTTP / REST
                    │ Axios · /api/v1/*
┌───────────────────▼─────────────────────────────────────┐
│                    FastAPI Backend                        │
│  Python 3.11 · Async · Pydantic v2 · Loguru             │
│  /stocks/* routes    /portfolio/* routes                 │
└────┬──────────────────────────┬───────────────────────── ┘
     │                          │
┌────▼────┐              ┌──────▼──────┐
│ Redis   │              │ PostgreSQL  │
│ Cache   │              │ Primary DB  │
│ TTL:    │              │             │
│ 24h/1h  │              │ 5 tables    │
└────┬────┘              └──────┬──────┘
     │                          │
┌────▼────────────────────────────────┐
│         Celery + Celery Beat         │
│  worker: data refresh tasks          │
│  beat:   nightly/hourly schedule     │
└──────────────────┬───────────────── ┘
                   │
    ┌──────────────┴──────────────┐
    │                             │
┌───▼────┐              ┌─────────▼──────────┐
│yfinance│              │ stockanalysis.com   │
│ free   │              │ httpx scrape        │
│ 3–4yr  │              │ 10yr history        │
└────────┘              └────────────────────┘
```

### Why two data sources?
yfinance is free and reliable but only returns 3–4 years of annual statements. Quality investing demands 10 years. stockanalysis.com displays 10-year tables publicly — we scrape them with polite delays and cache aggressively so we never hit them more than necessary.

---

## 8. Full Tech Stack

### Frontend

| Layer | Technology | Why |
|---|---|---|
| Framework | React 18 + Vite | Fast dev, HMR, ESM build |
| Styling | TailwindCSS v3 | Utility-first, no runtime cost |
| Charts | Recharts + custom SVG | Recharts for line/area; custom SVG for radar, donut, heatmap, waterfall |
| State | Zustand | Minimal boilerplate, no context hell |
| Data fetching | TanStack Query v5 | Cache, stale-while-revalidate, devtools |
| HTTP | Axios | Interceptors, base URL, error handling |
| Fonts | DM Mono + Syne | Via Google Fonts — mono for numbers, sans for headings |
| Animation | CSS keyframes + Intersection Observer | No runtime lib; SVG draw animations, scroll triggers |
| Icons | Lucide React | Consistent, tree-shakeable |

### Backend

| Layer | Technology | Why |
|---|---|---|
| Framework | FastAPI (Python 3.11) | Async, auto OpenAPI docs, fast |
| ORM | SQLAlchemy 2.0 async | Type-safe, async sessions |
| Migrations | Alembic | Version-controlled schema changes |
| Database | PostgreSQL 16 | Relational, robust, free |
| Cache | Redis 7 | Key-value TTL cache for scraped data |
| Task queue | Celery | Background refresh jobs |
| Scheduler | Celery Beat | Cron-style schedules |
| Validation | Pydantic v2 | Schemas + settings management |
| Finance data | yfinance | Prices, basic fundamentals, beta |
| Scraping | httpx + BeautifulSoup4 | stockanalysis.com 10yr data |
| Resilience | Tenacity | Retry with exponential backoff |
| Logging | Loguru | Structured, coloured dev logs |
| Container | Docker Compose | One-command local stack |

### Data sources

| Source | Fetches | Method | Cache TTL |
|---|---|---|---|
| yfinance | Prices, income statement, balance sheet, cashflow, beta, metadata | Python library | Prices: 1hr, Fundamentals: 24hr |
| stockanalysis.com | 10yr income statement tables, 10yr balance sheet | httpx + BeautifulSoup4 | 24hr |
| SPY (via yfinance) | Benchmark performance data | yfinance | 1hr |

---

## 9. Design System

### Visual identity
**Name:** Alphavault  
**Tone:** Premium fintech — Bloomberg terminal meets a well-designed SaaS tool. Data-dense but never cluttered. Dark, focused, professional.

### Colour palette

```
Background        #07080D   Near-black, slightly blue-tinted
Surface           #0C0E15   Cards, sidebar — slightly lifted from bg
Card              #10131C   Inner cards, table rows
Border            #1A1F2E   Default borders
Border bright     #232840   Hover borders, active states

Teal (primary)    #00D4AA   Primary accent — positive, active, pass
Teal dim          rgba(0,212,170,0.10)   Teal background tint
Teal glow         0 0 24px rgba(0,212,170,0.35)   Drop shadow / glow

Amber (warning)   #F5A623   Watch states, implied growth, warn
Red (danger)      #FF4D6A   Fail states, negative P&L
Blue (info)       #4D9EFF   Info states, secondary data lines
Purple            #A78BFA   Tertiary data, 3rd compare ticker

Text              #DDE3F0   Primary readable text
Mid               #7A859E   Secondary text, descriptions
Muted             #3D4560   Labels, timestamps, eyebrows
```

### Typography

```
Display / headings:   Syne 800, letter-spacing -0.03em
                      Used for: section titles, stock names
                      
Body / UI text:       Syne 400/600
                      Used for: descriptions, alert titles

Data / numbers:       DM Mono 300/400/500, letter-spacing 0.03em
                      Used for: all numbers, tickers, labels,
                               code-like UI elements
```

### Quality state colours

| State | Colour | When |
|---|---|---|
| Pass | `#00D4AA` (teal) | Value meets threshold |
| Warn | `#F5A623` (amber) | Within 20% of threshold |
| Fail | `#FF4D6A` (red) | Does not meet threshold |

### Component conventions

**Cards:**
```
background: var(--card)
border: 1px solid var(--border)
border-radius: 16px
padding: 24px
```

**Tag chips:**
```
border-radius: 20px
font-family: var(--mono)
font-size: 9px
letter-spacing: 0.06em
border: 1px solid
padding: 3px 9px
```
Colour variants: sector (blue tint) · country (teal tint) · cap (purple tint)

**Section eyebrow:**
```
DM Mono 9px · letter-spacing 0.22em · uppercase · var(--muted)
Preceded by 18px horizontal rule in same colour
Example: "── 02 · Quality Analysis"
```

**Section title:**
```
Syne 800 · clamp(28px, 3.5vw, 48px) · letter-spacing -0.03em
<em> tags render as teal, non-italic
Example: "MSFT Quality <em>Scorecard</em>"
```

---

## 10. Layout System

### Page structure
```
body (overflow: hidden, height: 100vh)
└── div (display: flex)
    ├── <Sidebar>        68px fixed, full height
    └── <main>           flex: 1, overflow-y: scroll
        ├── <ProgressBar>  sticky top, 2px teal→blue gradient
        ├── <SearchSection>      id="s-search"
        ├── <QualitySection>     id="s-quality"
        ├── <ValuationSection>   id="s-valuation"
        ├── <CompareSection>     id="s-compare"
        ├── <PortfolioSection>   id="s-portfolio"
        └── <AlertsSection>      id="s-alerts"
```

### Sidebar behaviour
- 68px wide, fixed, full height
- Logo at top: 38×38px teal/blue gradient rounded square
- 6 nav buttons with icon + 8px label
- Visual separator between Compare (§4) and Portfolio (§5)
- Active: teal background tint + 2px left accent bar with glow
- Click: smooth-scrolls main container to target section
- Active detection: Intersection Observer, threshold 0.3

### Scroll progress bar
- `position: sticky; top: 0; height: 2px`
- `background: linear-gradient(90deg, #00D4AA, #4D9EFF)`
- Width tracks `scrollTop / (scrollHeight - clientHeight) * 100`
- `box-shadow: 0 0 10px rgba(0,212,170,0.5)`

### Section anatomy
Every section:
- `min-height: 100vh`
- `padding: 56px 52px`
- `border-bottom: 1px solid var(--border)`
- Eyebrow + title block
- Content area (section-specific)

---

## 11. Section Summary

| # | ID | Purpose | Key components | Data source |
|---|---|---|---|---|
| 1 | `s-search` | Find and identify a stock | Search bar, stock result card, sparkline | `/stocks/search`, `/stocks/{ticker}`, `/stocks/{ticker}/prices` |
| 2 | `s-quality` | Evaluate quality criteria | Radar chart, 6 criterion cards, 6 trend charts, 3yr/10yr toggle | `/stocks/{ticker}/fundamentals` |
| 3 | `s-valuation` | Assess intrinsic value | DCF waterfall, adjustable inputs, reverse DCF, sensitivity heatmap | `/stocks/{ticker}/dcf`, `/stocks/{ticker}/reverse-dcf` |
| 4 | `s-compare` | Compare multiple stocks | Ticker selector, overlay chart, metric tabs, scorecard table | `/stocks/compare` |
| 5 | `s-portfolio` | Track holdings and allocation | Stats strip, holdings table, add drawer, donut charts, performance chart | `/portfolio/*` |
| 6 | `s-alerts` | Monitor portfolio health | Auto-generated alert cards by state | Derived from cached portfolio data, no extra API calls |

---

## 12. Data Model Summary

### Five database tables

| Table | Purpose | Key fields |
|---|---|---|
| `stocks` | Master stock metadata | ticker, name, sector, industry, country, market_cap, market_cap_category |
| `fundamentals` | Annual financial data per stock | ticker, fiscal_year, roce, revenue_growth, fcf_growth, eps_growth, lt_debt_to_fcf, peg_ratio + raw financials |
| `prices` | Daily OHLCV prices | ticker, price_date, close, adj_close, volume |
| `portfolio_holdings` | User's holdings | ticker, shares, avg_buy_price, buy_date, is_active |
| `portfolio_snapshots` | Daily portfolio value history | snapshot_date, total_value, total_cost, holdings_json |

### Data flow for a new ticker
```
User searches "ASML"
  → Check DB: not found
  → Call yfinance: get metadata, 4yr financials, prices
  → Scrape stockanalysis.com: get 10yr income + balance sheet
  → Merge: combine both sources, compute derived metrics (ROCE, growth rates)
  → Save: write all rows to DB
  → Cache: write JSON to Redis with 24hr TTL
  → Return: full FundamentalsResponse to frontend
  
Next request for ASML (within 24hr):
  → Cache hit: return Redis value instantly (no DB, no scrape)
```

---

## 13. API Surface

### Stock endpoints
```
GET  /api/v1/stocks/search?q={query}                    Search by ticker/name
GET  /api/v1/stocks/{ticker}                            Stock metadata
GET  /api/v1/stocks/{ticker}/fundamentals               10yr quality data
GET  /api/v1/stocks/{ticker}/prices?period=10y          Price history
GET  /api/v1/stocks/compare?tickers=MSFT,AAPL,GOOGL     Multi-stock compare
POST /api/v1/stocks/{ticker}/dcf                        Compute DCF (body: inputs)
GET  /api/v1/stocks/{ticker}/reverse-dcf                Reverse DCF
```

### Portfolio endpoints
```
GET    /api/v1/portfolio/holdings                       List all holdings
POST   /api/v1/portfolio/holdings                       Add holding
PUT    /api/v1/portfolio/holdings/{id}                  Update holding
DELETE /api/v1/portfolio/holdings/{id}                  Soft-delete holding
GET    /api/v1/portfolio/stats                          Totals, beta, quality avg
GET    /api/v1/portfolio/allocations                    Country/sector/cap breakdowns
GET    /api/v1/portfolio/performance                    Historical value vs SPY
```

---

## 14. Animation Philosophy

All animations serve a purpose — they either orient the user or confirm that data has arrived. No decorative animation.

### Principles
- **Draw on arrival:** Charts animate in when data loads, not before
- **Draw on scroll:** SVG lines draw when their section enters the viewport (Intersection Observer, threshold 0.2)
- **Once only:** Scroll-triggered animations do not replay on scroll back
- **Staggered:** Multiple elements in a group stagger by 60–80ms to feel organic
- **Fast:** Nothing slower than 1.2s — data tools need to feel snappy

### Animation inventory

| Element | Animation | Duration | Trigger |
|---|---|---|---|
| Stock result card | fadeUp (translateY + opacity) | 0.4s ease | Data arrives |
| Radar polygon | scale 0→1 | 0.6s ease-out | Section enters viewport |
| Criteria progress bars | width 0→N% staggered 80ms | 0.8s ease-out | Section enters viewport |
| Mini trend lines | stroke-dashoffset draw | 1.2s ease-out | Section enters viewport |
| DCF waterfall bars | height 0→N staggered 60ms | 0.6s ease-out | Section enters viewport |
| Donut ring segments | stroke-dasharray draw | 1.0s | Section enters viewport |
| Scroll progress bar | width%, linear | 0.08s | Every scroll event |
| Sidebar active state | background + border | 0.18s | Scroll spy fires |
| Pulsing quality dot | opacity 1→0.4→1 | 2s infinite | Always |
| Scroll cue arrow | translateY 0→5px | 1.8s infinite | Always |

---

## 15. Frontend State Management

### Zustand store shape
```js
{
  selectedTicker:    string | null      // Stock being researched in §1–§3
  compareTickers:    string[]           // Up to 5 tickers in §4
  activeSection:     string             // Currently visible section ID

  setSelectedTicker: (ticker) => void
  addCompareTicker:  (ticker) => void
  removeCompareTicker: (ticker) => void
  setActiveSection:  (id) => void
}
```

### TanStack Query cache configuration
```
fundamentals:   staleTime 24h  (matches Redis TTL)
prices:         staleTime 1h   (matches Redis TTL)
portfolio:      staleTime 30s  (near-live)
compare:        staleTime 24h
dcf:            staleTime 0    (user inputs — never stale)
reverse-dcf:    staleTime 1h
```

### Cross-section data sharing
The Compare section pre-populates with `selectedTicker` from Search. The Alerts section reads from the same TanStack Query cache as the Portfolio section — zero extra API calls. This is by design: alerts are a read-only view of already-fetched data.

---

## 16. File Structure (Complete)

```
alphavault/
├── docker-compose.yml
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   └── app/
│       ├── main.py                    FastAPI app, CORS, lifespan
│       ├── worker.py                  Celery app + Beat schedule + tasks
│       ├── core/
│       │   └── config.py              Pydantic settings
│       ├── db/
│       │   ├── session.py             Async engine + session + Base
│       │   └── cache.py               Redis helpers (get/set/delete)
│       ├── models/
│       │   └── models.py              5 SQLAlchemy ORM models
│       ├── schemas/
│       │   └── schemas.py             All Pydantic schemas
│       ├── services/
│       │   ├── data_fetcher.py        yfinance + stockanalysis.com
│       │   └── dcf.py                 DCF, reverse DCF, quality scoring
│       └── api/routes/
│           ├── stocks.py              Stock endpoints
│           └── portfolio.py           Portfolio endpoints
│
└── frontend/
    ├── Dockerfile
    ├── index.html
    ├── vite.config.js
    ├── tailwind.config.js
    ├── package.json
    └── src/
        ├── main.jsx
        ├── App.jsx                    Root — sections assembled here
        ├── styles/
        │   └── globals.css            Tokens, resets, keyframes
        ├── api/
        │   ├── client.js              Axios instance
        │   ├── stocks.js              Stock API calls
        │   └── portfolio.js           Portfolio API calls
        ├── store/
        │   └── useAppStore.js         Zustand store
        ├── hooks/
        │   ├── useScrollSpy.js
        │   ├── useFundamentals.js
        │   ├── usePriceHistory.js
        │   ├── useDCF.js
        │   ├── useCompare.js
        │   └── usePortfolio.js
        ├── lib/
        │   ├── quality.js             CRITERIA, getState, generateAlerts
        │   └── formatters.js          fmtCurrency, fmtPct, fmtLarge
        └── components/
            ├── layout/
            │   ├── Sidebar.jsx
            │   └── ProgressBar.jsx
            ├── search/
            │   ├── SearchSection.jsx
            │   ├── SearchBar.jsx
            │   └── StockResultCard.jsx
            ├── quality/
            │   ├── QualitySection.jsx
            │   ├── RadarChart.jsx
            │   ├── CriteriaGrid.jsx
            │   ├── CriterionCard.jsx
            │   └── MiniTrendChart.jsx
            ├── valuation/
            │   ├── ValuationSection.jsx
            │   ├── DCFCard.jsx
            │   ├── DCFWaterfallChart.jsx
            │   ├── DCFInputs.jsx
            │   └── ReverseDCFCard.jsx
            ├── compare/
            │   ├── CompareSection.jsx
            │   ├── TickerSelector.jsx
            │   ├── CompareLineChart.jsx
            │   └── ScorecardTable.jsx
            ├── portfolio/
            │   ├── PortfolioSection.jsx
            │   ├── StatsStrip.jsx
            │   ├── HoldingsTable.jsx
            │   ├── AddHoldingDrawer.jsx
            │   ├── DonutChart.jsx
            │   └── PerformanceChart.jsx
            ├── alerts/
            │   ├── AlertsSection.jsx
            │   └── AlertCard.jsx
            └── ui/
                ├── Skeleton.jsx
                ├── ErrorCard.jsx
                ├── Pill.jsx
                └── Tag.jsx
```

---

## 17. Feature Parity Checklist (Decommission Gate)

Before StockSight is removed, every item below must be ✅ in Alphavault.

### Preserved from StockSight
- [ ] Search by ticker and see key metrics
- [ ] Gross Margin displayed (note: not in original 6 quality criteria — include as supplementary metric in fundamentals response)
- [ ] PEG Ratio tracked and colour-coded
- [ ] Revenue Growth tracked and colour-coded
- [ ] ROCE tracked and colour-coded
- [ ] FCF Growth tracked and colour-coded
- [ ] LT Debt / FCF tracked and colour-coded
- [ ] DCF Margin of Safety computed and displayed
- [ ] Compare up to 5 stocks side by side
- [ ] Green / amber / red threshold colouring
- [ ] No login required — single-user mode
- [ ] Works with any yfinance-recognised ticker (international included)

### New in Alphavault
- [ ] 10 years of annual data (vs 3–4)
- [ ] Persistent DB storage
- [ ] Background nightly data refresh
- [ ] Portfolio holdings with CRUD
- [ ] Live P&L per holding
- [ ] Portfolio allocation donuts (country, sector, cap)
- [ ] Portfolio beta
- [ ] 10yr performance chart vs S&P 500
- [ ] DCF waterfall chart with adjustable inputs
- [ ] Reverse DCF with sensitivity heatmap
- [ ] Quality radar chart
- [ ] 10yr trend chart per metric
- [ ] 3yr / 10yr quality average toggle
- [ ] Auto-generated portfolio health alerts
- [ ] Smooth scroll single-page experience
- [ ] Animated charts on scroll entry

---

## 18. Sub-Spec Index

| File | Phase | Contents |
|---|---|---|
| `spec-backend-services.md` | 1 | `data_fetcher.py` + `dcf.py` function-by-function spec |
| `spec-backend-infra.md` | 2 | Docker Compose, DB models, Alembic, Celery tasks |
| `spec-backend-api.md` | 2 | FastAPI routes, Pydantic schemas, Redis caching, all endpoints |
| `spec-frontend-layout.md` | 3 | Vite/Tailwind scaffold, Sidebar, ProgressBar, design tokens, shared utilities |
| `spec-section-search.md` | 3 | Section 01 — Search bar, stock result card, sparkline |
| `spec-section-quality.md` | 3 | Section 02 — Radar, criteria cards, 6 trend charts |
| `spec-section-valuation.md` | 3 | Section 03 — DCF waterfall, reverse DCF heatmap |
| `spec-section-compare.md` | 3 | Section 04 — Ticker selector, overlay chart, scorecard |
| `spec-section-portfolio.md` | 3 | Section 05 — Holdings table, donuts, performance chart |
| `spec-section-alerts.md` | 3 | Section 06 — Alert generation, alert cards |

**Reading order for a new contributor:**
1. This document (design brief)
2. `spec-backend-services` — understand the data and logic layer
3. `spec-backend-infra` — understand the infrastructure
4. `spec-backend-api` — understand the HTTP surface
5. `spec-frontend-layout` — understand the shell and design system
6. Section specs in order (search → quality → valuation → compare → portfolio → alerts)

---

*End of design brief — v1.0*
*Project: Alphavault · Source: github.com/roel-karstens/stocksight*
