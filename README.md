| `portfolio_snapshots`| Daily portfolio value history  |

---

## 🛠️ Quick Start (Dev)

```bash
# Clone
git clone git@github.com:roel-karstens/StockSight.git
cd StockSight

# Start all services (backend, db, redis, worker, beat)
docker compose up --build

# Open API docs
open http://localhost:8000/docs
```

---

## 📝 Migration Note

The legacy Streamlit app remains available during migration. The new backend and frontend are built in parallel. See the `features/` folder for detailed specs and migration strategy.

---

## 📚 Further Reading

- [spec-design-brief.md](features/spec-design-brief.md) — Project vision, user journey, design system
- [spec-backend-services.md](features/spec-backend-services.md) — Data & logic layer
- [spec-backend-infra.md](features/spec-backend-infra.md) — Infrastructure & orchestration
- [spec-backend-api.md](features/spec-backend-api.md) — API surface & schemas

---

## License

MIT
- Animated, responsive UI

---

## 🗄️ Backend API

All endpoints documented at `/docs` (Swagger UI):

**Stock endpoints:**
- `GET  /api/v1/stocks/search?q={query}` — Search by ticker/name
- `GET  /api/v1/stocks/{ticker}` — Stock metadata
- `GET  /api/v1/stocks/{ticker}/fundamentals` — 10yr quality data
- `GET  /api/v1/stocks/{ticker}/prices?period=10y` — Price history
- `GET  /api/v1/stocks/compare?tickers=MSFT,AAPL,GOOGL` — Multi-stock compare
- `POST /api/v1/stocks/{ticker}/dcf` — Compute DCF
- `GET  /api/v1/stocks/{ticker}/reverse-dcf` — Reverse DCF

**Portfolio endpoints:**
- `GET    /api/v1/portfolio/holdings` — List all holdings
- `POST   /api/v1/portfolio/holdings` — Add holding
- `PUT    /api/v1/portfolio/holdings/{id}` — Update holding
- `DELETE /api/v1/portfolio/holdings/{id}` — Remove holding
- `GET    /api/v1/portfolio/stats` — Totals, beta, quality avg
- `GET    /api/v1/portfolio/allocations` — Country/sector/cap breakdowns
- `GET    /api/v1/portfolio/performance` — Historical value vs SPY

---

## 🗃️ Data Model

| Table                | Purpose                        |
|----------------------|--------------------------------|
| `stocks`             | Master stock metadata          |
| `fundamentals`       | Annual financial data per stock|
| `prices`             | Daily OHLCV prices             |
| `portfolio_holdings` | User's holdings                |
| `portfolio_snapshots`| Daily portfolio value history  |
- stockanalysis.com (10yr financials via scraping)

---

## 🔑 Core Features

- 10 years of annual data (yfinance + stockanalysis.com)
- Persistent DB storage (PostgreSQL)
- Background refresh (Celery Beat)
- Redis caching (configurable TTL)
- Portfolio tracking (CRUD, daily snapshots)
- Allocation & performance charts
- Portfolio beta & quality alerts
- DCF & reverse DCF tools
- Quality radar & trend charts
- Animated, responsive UI

# 📈 StockSight — Quality Investing Dashboard

StockSight is a full-stack, production-grade quality investing dashboard. Research any stock, compare up to 5 side-by-side, and track your portfolio’s health with 10 years of financial data, advanced valuation tools, and persistent storage.

---

## 🚀 What is StockSight?

StockSight replaces the original Streamlit app with a modern, service-oriented architecture:

- **Single-page React frontend**: Smooth scroll, 6 research/portfolio sections, beautiful charts, and instant feedback.
- **FastAPI backend**: Async Python, robust REST API, OpenAPI docs, and background data refresh.
- **PostgreSQL & Redis**: Persistent storage and fast caching.
- **Celery**: Automated nightly and hourly data refresh.

---

## 🧭 User Journey

The app is a single scrollable page with 6 sections:

1. **Search** — Find a stock, see quality badge & sparkline
2. **Quality** — Radar chart, 6 quality criteria, 10yr trends
3. **Valuation** — DCF intrinsic value, reverse DCF heatmap
4. **Compare** — Overlay charts, scorecard table vs 4 others
5. **Portfolio** — Holdings, allocation donuts, performance
6. **Alerts** — Auto-generated health cards from portfolio

---

## 🏗️ Architecture & Tech Stack

**Frontend:** React 18, Vite, TailwindCSS, Recharts, Zustand, TanStack Query, Axios  
**Backend:** FastAPI (Python 3.11), SQLAlchemy (async), Alembic, Pydantic, Loguru  
**Infra:** PostgreSQL 16, Redis 7, Celery, Docker Compose

**Data sources:**
- yfinance (prices, fundamentals, beta)
- stockanalysis.com (10yr financials via scraping)

## Metrics

| Metric | What it tells you | 🟢 Good | 🔴 Bad |
|--------|-------------------|---------|--------|
| **Gross Margin** | Pricing power & cost efficiency | ≥ 50% | < 20% |
| **PEG Ratio** | Growth-adjusted valuation | ≤ 2.0 | > 3.0 |
| **Revenue Growth** | Top-line momentum | > 10% | < 0% |
| **ROCE** | Capital efficiency | ≥ 15% | < 5% |
| **FCF Growth** | Cash generation trend | > 10% | < 0% |
| **LT Debt / FCF** | Debt sustainability | < 4.0x | > 5.0x |
| **DCF Margin of Safety** | Intrinsic value vs. market price | ≥ +20% | < −20% |

## Quick Start

```bash
# Clone
git clone git@github.com:roel-karstens/StockSight.git
cd StockSight

# Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
streamlit run app.py
```

Open http://localhost:8501, type a ticker (e.g. `MSFT`), and click **➕ Add**.

## How It Works

- **Data**: All financial data comes from [Yahoo Finance](https://finance.yahoo.com/) via the `yfinance` library — no API key needed.
- **Metrics**: Computed from raw income statements, balance sheets, and cash flow statements.
- **DCF Model**: Two-stage discounted cash flow (10-year projection at estimated FCF growth → terminal value at 3% perpetual growth, discounted at 10% WACC).
- **Charts**: Interactive Plotly charts with dashed threshold reference lines.
- **Caching**: Data is cached for 1 hour via `st.cache_data` to avoid repeated API calls.

## Project Structure

```
StockSight/
├── app.py              # Streamlit entry point
├── data/
│   ├── fetcher.py      # yfinance data fetching + caching
│   └── metrics.py      # All 7 metric calculations
├── ui/
│   ├── charts.py       # Plotly chart builders
│   └── indicators.py   # Threshold config & 🟢🟡🔴 logic
├── requirements.txt
├── POC.MD              # Design document
└── README.md
```

## Data Source

Yahoo Finance typically provides 3–4 years of annual financial statements. The dashboard works best for US-listed stocks but supports any ticker that `yfinance` recognizes (international included).

## License

MIT
