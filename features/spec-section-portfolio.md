# spec-section-portfolio.md
# Section 05 — Portfolio

> **Depends on:** Frontend layout complete, `src/api/portfolio.js` created  
> **Goal:** Holdings table with live P&L, 3 allocation donuts, performance chart vs S&P 500.  
> **Done when:** Adding a holding persists to DB, table shows live P&L, donuts reflect correct allocations, performance chart renders.

---

## Files to Create

```
src/
├── api/portfolio.js
├── hooks/usePortfolio.js
└── components/portfolio/
    ├── PortfolioSection.jsx
    ├── StatsStrip.jsx
    ├── HoldingsTable.jsx
    ├── AddHoldingDrawer.jsx
    ├── DonutChart.jsx
    └── PerformanceChart.jsx
```

---

## File: `src/api/portfolio.js`

```js
import { api } from './client'

export const portfolioApi = {
  getHoldings:    ()          => api.get('/portfolio/holdings'),
  addHolding:     (payload)   => api.post('/portfolio/holdings', payload),
  updateHolding:  (id, data)  => api.put(`/portfolio/holdings/${id}`, data),
  deleteHolding:  (id)        => api.delete(`/portfolio/holdings/${id}`),
  getStats:       ()          => api.get('/portfolio/stats'),
  getAllocations:  ()          => api.get('/portfolio/allocations'),
  getPerformance: ()          => api.get('/portfolio/performance'),
}
```

---

## File: `src/hooks/usePortfolio.js`

```js
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { portfolioApi } from '../api/portfolio'

export function useHoldings() {
  return useQuery({
    queryKey: ['holdings'],
    queryFn: portfolioApi.getHoldings,
    staleTime: 30_000,
  })
}

export function usePortfolioStats() {
  return useQuery({
    queryKey: ['portfolio-stats'],
    queryFn: portfolioApi.getStats,
    staleTime: 30_000,
  })
}

export function useAllocations() {
  return useQuery({
    queryKey: ['allocations'],
    queryFn: portfolioApi.getAllocations,
    staleTime: 30_000,
  })
}

export function usePerformance() {
  return useQuery({
    queryKey: ['performance'],
    queryFn: portfolioApi.getPerformance,
    staleTime: 3_600_000,
  })
}

export function useAddHolding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: portfolioApi.addHolding,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['holdings'] })
      qc.invalidateQueries({ queryKey: ['portfolio-stats'] })
      qc.invalidateQueries({ queryKey: ['allocations'] })
    },
  })
}

export function useDeleteHolding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: portfolioApi.deleteHolding,
    onMutate: async (id) => {
      // Optimistic update
      await qc.cancelQueries({ queryKey: ['holdings'] })
      const prev = qc.getQueryData(['holdings'])
      qc.setQueryData(['holdings'], (old) => old?.filter(h => h.id !== id) ?? [])
      return { prev }
    },
    onError: (_err, _id, ctx) => qc.setQueryData(['holdings'], ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: ['holdings'] }),
  })
}
```

---

## Component: `<StatsStrip />`

### Props
```js
{ stats: PortfolioStats }
```

### Layout
5-column grid of stat boxes:

| Stat | Value | Color rule |
|---|---|---|
| Total Value | `fmtCurrency(total_value)` | teal |
| Unrealised P&L | `fmtCurrency(total_pnl)` | teal if ≥0, red if <0 |
| Total Return | `fmtPct(total_pnl_pct, true)` | teal if ≥0, red if <0 |
| Portfolio Beta | `beta?.toFixed(2) ?? '—'` | `var(--text)` |
| Avg Quality | `quality_score_avg?.toFixed(1) ?? '—'` / 6 | teal |

Each stat box:
```
background: var(--card)
border: 1px solid var(--border)
border-radius: 12px
padding: 16px 18px
```
- Label: DM Mono 8px uppercase muted
- Value: DM Mono 20px, -0.02em tracking

---

## Component: `<HoldingsTable />`

### Props
```js
{
  holdings: HoldingOut[]
  onDelete: (id: number) => void
  onEdit: (holding: HoldingOut) => void
  onAdd: () => void       // opens AddHoldingDrawer
}
```

### Columns
| Column | Notes |
|---|---|
| Ticker | DM Mono teal bold |
| Company | `var(--text)` |
| Shares | DM Mono right-aligned |
| Avg Cost | `fmtCurrency` |
| Current | `fmtCurrency`, `—` if null |
| Value | `fmtCurrency(current_value)`, `—` if null |
| P&L% | `fmtPct(unrealised_pnl_pct, true)`, teal ≥0, red <0 |
| Quality | 6 dots (6px circles): filled teal if pass, `var(--border2)` if fail (derived from `avg_10yr`) |
| Actions | Pencil icon (edit) + × icon (delete), appear on row hover |

### Quality dots
Quality dot fill for each criterion key in order: `roce_ok → revenue_growth_ok → fcf_growth_ok → eps_growth_ok → lt_debt_fcf_ok → peg_ok`

```jsx
const qualityKeys = ['roce_ok','revenue_growth_ok','fcf_growth_ok','eps_growth_ok','lt_debt_fcf_ok','peg_ok']
{qualityKeys.map(k => (
  <div key={k} style={{ width: 6, height: 6, borderRadius: '50%', background: holding.quality?.[k] ? 'var(--teal)' : 'var(--border2)', boxShadow: holding.quality?.[k] ? '0 0 4px var(--teal)' : 'none' }} />
))}
```

> Note: `HoldingOut` from API does not include `quality` — fetch separately from `useFundamentals` per ticker, or include `avg_10yr` in holding response. **Preferred:** extend `HoldingOut` schema to include `avg_10yr: QualityCriteria | None`.

### Table styling
```css
border-collapse: separate;
border-spacing: 0 5px;
font-family: var(--mono);
font-size: 11px;
```
- `th`: 8px DM Mono uppercase muted, border-bottom `var(--border)`
- `td`: `background: var(--card)`, padding `13px 14px`
- First `td`: `border-radius: 10px 0 0 10px`
- Last `td`: `border-radius: 0 10px 10px 0`
- Row hover: `background: #14192A`

### `+ Add holding` button
- Below the table
- Style: `border: 1px dashed var(--border2)`, `border-radius: 10px`, `padding: 10px`, full width, DM Mono 11px `var(--muted)`, cursor pointer
- On click: opens `<AddHoldingDrawer />`

### Empty state
- When `holdings.length === 0`:
```jsx
<div className="card" style={{ textAlign: 'center', padding: 48 }}>
  <div style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 12, marginBottom: 16 }}>
    No holdings yet.
  </div>
  <button onClick={onAdd}>+ Add First Holding</button>
</div>
```

---

## Component: `<AddHoldingDrawer />`

### Props
```js
{
  open: boolean
  onClose: () => void
  onSubmit: (payload: HoldingCreate) => void
  initialTicker?: string    // pre-fill from selectedTicker
}
```

### Layout
- Slide-in panel from the right, `position: fixed`, `top: 0, right: 0, bottom: 0`, `width: 380px`
- Background: `var(--surface)`, `border-left: 1px solid var(--border2)`
- Overlay: semi-transparent `rgba(0,0,0,0.5)` behind drawer
- Close button: `✕` top right

### Fields

| Field | Type | Validation |
|---|---|---|
| Ticker | text input (with search) | required, uppercase |
| Shares | number | required, > 0 |
| Avg Buy Price | number (USD) | required, > 0 |
| Buy Date | date input | required |
| Notes | textarea | optional |

### Ticker field behaviour
- On blur or after 300ms: calls `stocksApi.search(value)` to validate ticker exists
- Shows company name below if valid, error if not found

### Submit
- Button: `Add Holding`, full width, `background: var(--teal-dim)`, `border: 1px solid rgba(0,212,170,0.3)`, teal text
- On submit: calls `onSubmit(payload)`, then `onClose()`
- While mutating: button shows loading spinner, disabled

### No `<form>` element — use button `onClick` with state

---

## Component: `<DonutChart />`

### Props
```js
{
  title: string
  items: AllocationItem[]    // [{label, value, percentage}]
  colors: string[]           // CSS color strings
}
```

### Layout
```
[title]
┌──────────────────────────────┐
│  [SVG donut 120px]  [legend] │
└──────────────────────────────┘
```
- `display: grid; grid-template-columns: 120px 1fr; gap: 14px; align-items: center`
- Title above in 9px DM Mono uppercase muted

### SVG donut
```
viewBox: 0 0 120 120
cx: 60, cy: 60, r: 46
stroke-width: 18
```

Segments:
- Draw using `stroke-dasharray` and `stroke-dashoffset`
- Circumference: `2 × π × 46 ≈ 289`
- For each item: `dashLen = (percentage / 100) × 289`
- Stack by incrementing `stroke-dashoffset`

Centre:
```jsx
<text x="60" y="56" ...>{items.length}</text>
<text x="60" y="69" ...>{centerLabel}</text>
```
`centerLabel` examples: `"4 nations"`, `"3 sectors"`, `"2 cap sizes"`

Draw animation: `stroke-dasharray` animates from `0 289` to final value on Intersection Observer trigger.

### Legend
```jsx
{items.slice(0,5).map((item, i) => (
  <div key={item.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      <div style={{ width: 7, height: 7, borderRadius: '50%', background: colors[i] }} />
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--mid)' }}>{item.label}</span>
    </div>
    <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text)' }}>{item.percentage.toFixed(1)}%</span>
  </div>
))}
```

---

## Component: `<PerformanceChart />`

### Props
```js
{
  data: PortfolioPerformancePoint[]
}
```

### State
```js
const [period, setPeriod] = useState('10Y')
```

### Period filtering
```js
const PERIOD_MONTHS = { '1Y': 12, '3Y': 36, '5Y': 60, '10Y': 120, 'Max': Infinity }

const filtered = data.filter(p => {
  const cutoff = new Date()
  cutoff.setMonth(cutoff.getMonth() - PERIOD_MONTHS[period])
  return new Date(p.date) >= cutoff
})
```

### Normalisation
- Both series start at 0% on the first data point
- `portfolioReturn = (value / first_value - 1) × 100`
- `benchmarkReturn = (benchmark_value / first_benchmark - 1) × 100`

### Recharts implementation
```jsx
<ResponsiveContainer width="100%" height={200}>
  <AreaChart data={chartData} margin={{ top: 10, right: 10, bottom: 10, left: 40 }}>
    <defs>
      <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#00D4AA" stopOpacity={0.18} />
        <stop offset="100%" stopColor="#00D4AA" stopOpacity={0} />
      </linearGradient>
    </defs>
    <CartesianGrid stroke="var(--border)" strokeDasharray="0" vertical={false} />
    <XAxis dataKey="year" tick={{ fontFamily: 'var(--mono)', fontSize: 8, fill: 'var(--muted)' }} axisLine={false} tickLine={false} />
    <YAxis tick={{ fontFamily: 'var(--mono)', fontSize: 8, fill: 'var(--muted)' }} axisLine={false} tickLine={false} tickFormatter={v => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`} />
    <Tooltip content={<PerfTooltip />} />
    <ReferenceLine y={0} stroke="var(--border)" />
    <Area type="monotone" dataKey="portfolioReturn" stroke="#00D4AA" strokeWidth={2.5} fill="url(#portfolioGrad)" dot={false} />
    <Line type="monotone" dataKey="benchmarkReturn" stroke="var(--muted)" strokeWidth={1.5} dot={false} />
  </AreaChart>
</ResponsiveContainer>
```

### Header section (above chart)
```
┌───────────────────────────────────────────┐
│ 10-YEAR PERFORMANCE VS S&P 500            │
│ +279%          vs S&P 500 +183%           │
│                         [1Y][3Y][5Y][10Y][Max] │
│ ─── Portfolio   ─── S&P 500              │
└───────────────────────────────────────────┘
```
- `+279%`: DM Mono 30px teal
- `vs S&P 500 +183%`: DM Mono 13px muted
- Period pills: `<Pill>` components

---

## Component: `<PortfolioSection />`

```jsx
export function PortfolioSection() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { data: holdings, isLoading: holdingsLoading } = useHoldings()
  const { data: stats } = usePortfolioStats()
  const { data: allocations } = useAllocations()
  const { data: performance } = usePerformance()
  const addHolding = useAddHolding()
  const deleteHolding = useDeleteHolding()

  const DONUT_COLORS = ['var(--teal)', 'var(--blue)', 'var(--purple)', 'var(--amber)', 'var(--red)']

  return (
    <section id="s-portfolio" style={{ minHeight: '100vh', padding: '56px 52px' }}>
      <div className="sec-eyebrow">05 · My Portfolio</div>
      <h2 className="sec-title">Portfolio <em>Overview</em></h2>

      {stats && <StatsStrip stats={stats} />}

      {holdingsLoading
        ? <SkeletonCard height={240} />
        : <HoldingsTable
            holdings={holdings ?? []}
            onDelete={(id) => deleteHolding.mutate(id)}
            onEdit={(h) => { /* future: open edit drawer */ }}
            onAdd={() => setDrawerOpen(true)}
          />
      }

      {allocations && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
          <DonutChart title="By Country"    items={allocations.by_country}    colors={DONUT_COLORS} />
          <DonutChart title="By Sector"     items={allocations.by_sector}     colors={DONUT_COLORS} />
          <DonutChart title="By Market Cap" items={allocations.by_market_cap} colors={DONUT_COLORS} />
        </div>
      )}

      {performance && <PerformanceChart data={performance} />}

      <AddHoldingDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSubmit={(payload) => addHolding.mutate(payload)}
      />
    </section>
  )
}
```

---

## Verification Checklist

- [ ] Stats strip shows correct values from API
- [ ] Holdings table renders with all columns
- [ ] P&L column is green/red correctly
- [ ] Quality dots reflect actual criteria for each holding
- [ ] Row hover shows edit/delete icons
- [ ] Delete holding removes it from table optimistically
- [ ] `+ Add holding` button opens drawer
- [ ] Drawer pre-fills ticker from `selectedTicker` if set
- [ ] Submitting drawer form creates holding in DB and table updates
- [ ] Empty state shown when no holdings exist
- [ ] All 3 donuts render with correct proportions
- [ ] Donut segments animate on scroll-into-view
- [ ] Donut legend shows correct labels and percentages
- [ ] Performance chart renders portfolio + benchmark lines
- [ ] Period switching filters data correctly
- [ ] Return values normalised to start at 0%
- [ ] Chart X-axis shows correct year labels for period
