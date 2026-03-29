# spec-backend-infra.md
# Backend Infrastructure

> **Phase:** 2 (parallel with API) — Docker, Postgres, Redis, Celery  
> **Goal:** `docker compose up` starts all services, DB schema exists, Celery tasks run on schedule.  
> **Done when:** All 6 containers healthy, Alembic migrations applied, Celery beat logs show scheduled tasks firing.

---

## Services Overview

```
docker-compose.yml
├── db        PostgreSQL 16
├── redis     Redis 7
├── backend   FastAPI (uvicorn)
├── worker    Celery worker
├── beat      Celery beat scheduler
└── frontend  React/Vite (added in frontend phase)
```

---

## File: `docker-compose.yml`

### Service: `db`
```yaml
image: postgres:16-alpine
container_name: portfolio_db
environment:
  POSTGRES_USER: portfolio
  POSTGRES_PASSWORD: portfolio_secret
  POSTGRES_DB: portfolio_db
volumes:
  - postgres_data:/var/lib/postgresql/data
ports:
  - "5432:5432"
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U portfolio -d portfolio_db"]
  interval: 10s
  timeout: 5s
  retries: 5
```

### Service: `redis`
```yaml
image: redis:7-alpine
container_name: portfolio_redis
ports:
  - "6379:6379"
volumes:
  - redis_data:/data
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 10s
  timeout: 5s
  retries: 5
```

### Service: `backend`
```yaml
build:
  context: ./backend
  dockerfile: Dockerfile
container_name: portfolio_backend
environment:
  DATABASE_URL: postgresql+asyncpg://portfolio:portfolio_secret@db:5432/portfolio_db
  REDIS_URL: redis://redis:6379/0
  ENV: development
ports:
  - "8000:8000"
volumes:
  - ./backend:/app       # hot reload in dev
depends_on:
  db:    { condition: service_healthy }
  redis: { condition: service_healthy }
command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Service: `worker`
```yaml
build: { context: ./backend, dockerfile: Dockerfile }
container_name: portfolio_worker
environment:
  DATABASE_URL: postgresql+asyncpg://portfolio:portfolio_secret@db:5432/portfolio_db
  REDIS_URL: redis://redis:6379/0
volumes:
  - ./backend:/app
depends_on:
  db:    { condition: service_healthy }
  redis: { condition: service_healthy }
command: celery -A app.worker.celery_app worker --loglevel=info
```

### Service: `beat`
```yaml
build: { context: ./backend, dockerfile: Dockerfile }
container_name: portfolio_beat
environment:
  REDIS_URL: redis://redis:6379/0
volumes:
  - ./backend:/app
depends_on:
  - redis
command: celery -A app.worker.celery_app beat --loglevel=info
```

### Service: `frontend` *(added in frontend phase)*
```yaml
build: { context: ./frontend, dockerfile: Dockerfile }
container_name: portfolio_frontend
ports:
  - "3000:3000"
volumes:
  - ./frontend:/app
  - /app/node_modules
environment:
  VITE_API_URL: http://localhost:8000
depends_on:
  - backend
```

### Volumes
```yaml
volumes:
  postgres_data:
  redis_data:
```

---

## File: `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
```

---

## File: `backend/requirements.txt`

```
# Web framework
fastapi==0.111.0
uvicorn[standard]==0.29.0

# Database
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
psycopg2-binary==2.9.9

# Cache / Task queue
redis==5.0.4
celery==5.3.6

# Data fetching
yfinance==0.2.40
httpx==0.27.0
beautifulsoup4==4.12.3
lxml==5.2.1

# Data processing
pandas==2.2.2
numpy==1.26.4

# Validation
pydantic==2.7.1
pydantic-settings==2.2.1

# Utils
python-dotenv==1.0.1
tenacity==8.3.0
loguru==0.7.2
```

---

## File: `app/core/config.py`

```python
class Settings(BaseSettings):
    ENV: str = "development"
    APP_NAME: str = "Alphavault"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+asyncpg://portfolio:portfolio_secret@localhost:5432/portfolio_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    CACHE_TTL_PRICES: int = 3600        # 1 hour
    CACHE_TTL_FUNDAMENTALS: int = 86400  # 24 hours

    REQUEST_TIMEOUT: int = 30
    REQUEST_DELAY: float = 1.5           # polite scraping delay

    DCF_DEFAULT_WACC: float = 0.10
    DCF_DEFAULT_TERMINAL_GROWTH: float = 0.03
    DCF_DEFAULT_YEARS: int = 10

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

---

## File: `app/db/session.py`

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENV == "development",
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

## Database Models: `app/models/models.py`

### `Stock`
```python
__tablename__ = "stocks"

id                  Mapped[int]       primary_key
ticker              Mapped[str]       String(20), unique, index
name                Mapped[str|None]  String(255)
sector              Mapped[str|None]  String(100)
industry            Mapped[str|None]  String(100)
country             Mapped[str|None]  String(100)
exchange            Mapped[str|None]  String(50)
currency            Mapped[str|None]  String(10)
market_cap          Mapped[float|None]
market_cap_category Mapped[str|None]  String(20)
description         Mapped[str|None]  Text
website             Mapped[str|None]  String(255)
last_updated        Mapped[datetime|None]
created_at          Mapped[datetime]  default=now()

# Relationships
fundamentals → list[Fundamental]  cascade="all, delete-orphan"
prices       → list[Price]        cascade="all, delete-orphan"
holdings     → list[PortfolioHolding]
```

### `Fundamental`
```python
__tablename__ = "fundamentals"
UniqueConstraint("ticker", "fiscal_year")

id              Mapped[int]        primary_key
ticker          Mapped[str]        FK stocks.ticker, index
fiscal_year     Mapped[int]

# Quality criteria
roce            Mapped[float|None]
revenue_growth  Mapped[float|None]
fcf_growth      Mapped[float|None]
eps_growth      Mapped[float|None]
lt_debt_to_fcf  Mapped[float|None]
peg_ratio       Mapped[float|None]

# Raw financials
revenue             Mapped[float|None]
gross_profit        Mapped[float|None]
operating_income    Mapped[float|None]
net_income          Mapped[float|None]
ebitda              Mapped[float|None]
free_cash_flow      Mapped[float|None]
capital_employed    Mapped[float|None]
total_debt          Mapped[float|None]
long_term_debt      Mapped[float|None]
cash_and_equivalents Mapped[float|None]
shares_outstanding  Mapped[float|None]
eps                 Mapped[float|None]
book_value_per_share Mapped[float|None]
dividend_per_share  Mapped[float|None]

# Valuation
pe_ratio    Mapped[float|None]
ps_ratio    Mapped[float|None]
pb_ratio    Mapped[float|None]
ev_ebitda   Mapped[float|None]

created_at  Mapped[datetime] default=now()
```

### `Price`
```python
__tablename__ = "prices"
UniqueConstraint("ticker", "price_date")

id          Mapped[int]    primary_key
ticker      Mapped[str]    FK stocks.ticker, index
price_date  Mapped[date]   index
open        Mapped[float|None]
high        Mapped[float|None]
low         Mapped[float|None]
close       Mapped[float]
adj_close   Mapped[float|None]
volume      Mapped[int|None]
```

### `PortfolioHolding`
```python
__tablename__ = "portfolio_holdings"

id              Mapped[int]    primary_key
ticker          Mapped[str]    FK stocks.ticker, index
shares          Mapped[float]
avg_buy_price   Mapped[float]
buy_date        Mapped[date]
notes           Mapped[str|None]  Text
is_active       Mapped[bool]   default=True
created_at      Mapped[datetime]
updated_at      Mapped[datetime]  onupdate=now()
```

### `PortfolioSnapshot`
```python
__tablename__ = "portfolio_snapshots"

id              Mapped[int]    primary_key
snapshot_date   Mapped[date]   unique, index
total_value     Mapped[float]
total_cost      Mapped[float]
holdings_json   Mapped[dict]   JSON
created_at      Mapped[datetime]
```

---

## Alembic Setup

### Initialise
```bash
cd backend
alembic init alembic
```

### `alembic/env.py` changes
```python
from app.db.session import Base
from app.models.models import *   # import all models to populate metadata
from app.core.config import get_settings

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncpg", "+psycopg2"))
target_metadata = Base.metadata
```

### Generate first migration
```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

> **Note:** Alembic uses synchronous psycopg2 URL for migrations. Runtime uses asyncpg. Both point to the same DB.

---

## File: `app/worker.py`

### Celery App
```python
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
```

### Beat Schedule

| Task name | Schedule | Description |
|---|---|---|
| `refresh_all_fundamentals` | `crontab(hour=2, minute=0)` | Nightly 02:00 UTC |
| `refresh_all_prices` | `crontab(minute=0, hour="14-21")` | Hourly during market hours (14–21 UTC = 09–16 EST) |
| `snapshot_portfolio` | `crontab(hour=21, minute=30)` | Daily after market close |

### Task: `refresh_all_fundamentals`
- Reads all tickers from `stocks` table
- For each: calls `fetch_yfinance_financials(ticker)`, upserts results
- Logs failures, continues on error

### Task: `refresh_all_prices`
- Reads all tickers from `stocks` table
- For each: calls `fetch_price_history(ticker, period="5d")`
- Inserts only rows not already in `prices` table
- Commits per ticker

### Task: `snapshot_portfolio`
- Reads all active `PortfolioHolding` rows
- For each: fetches latest price, computes value
- Creates one `PortfolioSnapshot` row with `snapshot_date = date.today()`
- Skips if snapshot already exists for today

---

## Environment Files

### `backend/.env`
```env
DATABASE_URL=postgresql+asyncpg://portfolio:portfolio_secret@db:5432/portfolio_db
REDIS_URL=redis://redis:6379/0
ENV=development
CACHE_TTL_PRICES=3600
CACHE_TTL_FUNDAMENTALS=86400
REQUEST_TIMEOUT=30
REQUEST_DELAY=1.5
DCF_DEFAULT_WACC=0.10
DCF_DEFAULT_TERMINAL_GROWTH=0.03
DCF_DEFAULT_YEARS=10
```

### `frontend/.env` *(added in frontend phase)*
```env
VITE_API_URL=http://localhost:8000
```

---

## Verification Checklist

- [ ] `docker compose up` — all 6 containers start without error
- [ ] `docker compose ps` — all containers show `healthy` or `running`
- [ ] `docker compose logs backend` — no import errors, "Database tables ready"
- [ ] `docker compose logs worker` — "celery@... ready"
- [ ] `docker compose logs beat` — shows task schedule printed on startup
- [ ] `psql -U portfolio -d portfolio_db -c "\dt"` — shows all 5 tables
- [ ] `alembic upgrade head` runs without error
- [ ] Redis reachable: `docker compose exec redis redis-cli ping` → `PONG`
- [ ] Celery worker receives test task: `celery -A app.worker.celery_app call app.worker.tasks.refresh_all_prices`
- [ ] `PortfolioSnapshot` row created after manually triggering `snapshot_portfolio`
- [ ] After `docker compose down -v` and `docker compose up`, schema recreates cleanly
