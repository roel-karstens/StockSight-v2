# spec-section-compare.md
# Section 04 — Compare

> **Depends on:** Search section complete, `useFundamentals` working, Zustand store has `compareTickers`  
> **Goal:** User can add up to 5 tickers, view overlapping metric charts, and see a colour-coded scorecard table.  
> **Done when:** Adding 3 tickers renders overlapping lines in the chart, tab switching updates the chart metric, scorecard shows correct pass/warn/fail.

---

## Files to Create

```
src/
├── hooks/useCompare.js
└── components/compare/
    ├── CompareSection.jsx
    ├── TickerSelector.jsx
    ├── CompareLineChart.jsx
    └── ScorecardTable.jsx
```

---

## File: `src/hooks/useCompare.js`

```js
import { useQuery } from '@tanstack/react-query'
import { stocksApi } from '../api/stocks'

export function useCompare(tickers) {
  return useQuery({
    queryKey: ['compare', tickers],
    queryFn: () => stocksApi.compare(tickers),
    enabled: tickers.length >= 2,
    staleTime: 86_400_000,
  })
}
```

Response shape:
```js
{
  MSFT: {
    fundamentals: FundamentalOut[],
    avg_3yr: QualityCriteria,
    avg_10yr: QualityCriteria,
  },
  AAPL: { ... },
}
```

---

## Colour Palette

Tickers are assigned colours in order. Never reassign on removal — use index of ticker in the `compareTickers` array.

```js
export const TICKER_COLORS = [
  'var(--teal)',    // 0
  'var(--blue)',    // 1
  'var(--purple)',  // 2
  'var(--amber)',   // 3
  'var(--red)',     // 4
]

export const TICKER_PILL_STYLES = [
  { color: 'var(--teal)',   border: 'rgba(0,212,170,0.28)',   bg: 'rgba(0,212,170,0.08)'   },
  { color: 'var(--blue)',   border: 'rgba(77,158,255,0.28)',  bg: 'rgba(77,158,255,0.08)'  },
  { color: 'var(--purple)', border: 'rgba(167,139,250,0.28)', bg: 'rgba(167,139,250,0.08)' },
  { color: 'var(--amber)',  border: 'rgba(245,166,35,0.28)',  bg: 'rgba(245,166,35,0.08)'  },
  { color: 'var(--red)',    border: 'rgba(255,77,106,0.28)',  bg: 'rgba(255,77,106,0.08)'  },
]
```

---

## Component: `<TickerSelector />`

### Props
```js
{
  tickers: string[]                       // current list
  onAdd: (ticker: string) => void
  onRemove: (ticker: string) => void
}
```

### Layout
```
[MSFT ✕]  [AAPL ✕]  [GOOGL ✕]  [+ Add ticker]
```

### Existing ticker chips
- Styled per `TICKER_PILL_STYLES[index]`
- `✕` remove button: opacity 0.4, on click calls `onRemove(ticker)`
- Non-removable if only 1 ticker remains (hide `✕`)

### `+ Add ticker` button
- Dashed border `var(--border2)`, DM Mono 11px `var(--muted)`
- On click: shows inline `<SearchBar onSelect={onAdd} />` (reuse SearchBar component from search section)
- Closes after selection
- Hidden when 5 tickers already added

### Pre-population
- On section mount: if `selectedTicker` is set in Zustand store, auto-add it if `compareTickers` is empty

---

## Metric Tabs

```js
export const COMPARE_METRICS = [
  { key: 'roce',           label: 'ROCE',           unit: '%', threshold: 10,   direction: 'above' },
  { key: 'revenue_growth', label: 'Revenue Growth', unit: '%', threshold: 0.10, direction: 'above' },
  { key: 'fcf_growth',     label: 'FCF Growth',     unit: '%', threshold: 0.10, direction: 'above' },
  { key: 'eps_growth',     label: 'EPS Growth',     unit: '%', threshold: 0.10, direction: 'above' },
  { key: 'lt_debt_to_fcf', label: 'LT Debt / FCF',  unit: '×', threshold: 4,    direction: 'below' },
  { key: 'peg_ratio',      label: 'PEG Ratio',      unit: '',  threshold: 2,    direction: 'below' },
]
```

Tab bar: row of 6 `<Pill>` components, active pill highlights active metric.  
Clicking a tab: updates `activeMetric` state in `CompareSection`, no re-fetch.

---

## Component: `<CompareLineChart />`

### Props
```js
{
  data: Record<string, FundamentalOut[]>   // ticker → fundamentals array
  metric: string                           // e.g. 'roce'
  colors: Record<string, string>           // ticker → CSS color string
  threshold: number
  direction: 'above' | 'below'
  unit: string
}
```

### Implementation: Recharts `LineChart`

```jsx
<ResponsiveContainer width="100%" height={160}>
  <LineChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 44 }}>
    <CartesianGrid stroke="var(--border)" strokeDasharray="0" vertical={false} />
    <XAxis dataKey="year" tick={{ fontFamily: 'var(--mono)', fontSize: 8, fill: 'var(--muted)' }} axisLine={false} tickLine={false} />
    <YAxis tick={{ fontFamily: 'var(--mono)', fontSize: 8, fill: 'var(--muted)' }} axisLine={false} tickLine={false} tickFormatter={v => formatValue(v, unit)} />
    <Tooltip content={<CustomTooltip colors={colors} unit={unit} />} />
    <ReferenceLine y={threshold} stroke="var(--muted)" strokeDasharray="4 3" label={{ value: `${threshold}${unit}`, fill: 'var(--muted)', fontSize: 8, fontFamily: 'var(--mono)' }} />
    {Object.entries(data).map(([ticker, _, i]) => (
      <Line
        key={ticker}
        type="monotone"
        dataKey={ticker}
        stroke={colors[ticker]}
        strokeWidth={2.2}
        strokeDasharray={i >= 2 ? '6 3' : undefined}
        dot={false}
        activeDot={{ r: 4, fill: colors[ticker] }}
      />
    ))}
  </LineChart>
</ResponsiveContainer>
```

### Data preparation
```js
// Pivot: one row per year, columns per ticker
const years = [2015, 2016, ..., 2024]
const chartData = years.map(year => {
  const row = { year }
  Object.entries(data).forEach(([ticker, fundamentals]) => {
    const found = fundamentals.find(f => f.fiscal_year === year)
    row[ticker] = found?.[metric] ?? null
  })
  return row
})
```

### Custom tooltip
```jsx
function CustomTooltip({ active, payload, label, colors, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border2)', borderRadius: 8, padding: '8px 12px', fontFamily: 'var(--mono)', fontSize: 11 }}>
      <div style={{ color: 'var(--muted)', marginBottom: 6 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: colors[p.dataKey] }}>
          {p.dataKey}: {formatValue(p.value, unit)}
        </div>
      ))}
    </div>
  )
}
```

### Legend row
Above chart:
```jsx
<div style={{ display: 'flex', gap: 20 }}>
  {tickers.map((ticker, i) => (
    <div key={ticker} style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--mono)', fontSize: 10, color: TICKER_COLORS[i] }}>
      <div style={{ width: 18, height: 2, background: TICKER_COLORS[i], ...(i >= 2 ? { borderTop: `2px dashed ${TICKER_COLORS[i]}`, height: 0 } : {}) }} />
      {ticker}
    </div>
  ))}
</div>
```

---

## Component: `<ScorecardTable />`

### Props
```js
{
  tickers: string[]
  data: Record<string, { avg_10yr: QualityCriteria, fundamentals: FundamentalOut[] }>
  colors: Record<string, string>
}
```

### Layout
```
Criteria (10yr avg)  │  MSFT  │  AAPL  │  GOOGL
─────────────────────┼────────┼────────┼────────
ROCE > 10%           │ 38.2% ✓│ 52.1% ✓│ 24.8% ✓
Revenue Growth > 10% │ 14.8% ✓│  8.2% ⚠│ 12.3% ✓
FCF Growth > 10%     │ 18.3% ✓│ 11.4% ✓│ 16.7% ✓
EPS Growth > 10%     │ 16.1% ✓│ 18.9% ✓│  9.2% ⚠
LT Debt / FCF < 4×   │  1.8× ✓│  5.2× ✗│  0.4× ✓
PEG < 2              │  1.42 ✓│  1.81 ✓│  1.55 ✓
─────────────────────┼────────┼────────┼────────
Quality Score        │  6/6   │  4/6   │  4/6
```

### Cell state styling

Each data cell:
- Compute 10yr avg for the metric from `fundamentals` (not just `avg_10yr` bool — need the actual value)
- Call `getState(value, threshold, direction)`
- Apply:

| State | Text color | Background |
|---|---|---|
| pass | `var(--teal)` | `rgba(0,212,170,0.07)` |
| warn | `var(--amber)` | `rgba(245,166,35,0.06)` |
| fail | `var(--red)` | `rgba(255,77,106,0.06)` |

- Suffix: `✓` for pass, `⚠` for warn, `✗` for fail

### Score row
- Larger font (14px bold), same pass/warn/fail colouring
- Score is `avg_10yr.score` from API response

### Table styling
- `border-collapse: separate`, `border-spacing: 0 4px`
- DM Mono 11px
- Header: ticker names coloured per `colors[ticker]`
- Row hover: background `#14192A`
- First column: DM Mono 10px `var(--mid)`, left-aligned, `border-radius: 9px 0 0 9px`
- Last column: `border-radius: 0 9px 9px 0`

---

## Component: `<CompareSection />`

```jsx
export function CompareSection() {
  const { compareTickers, addCompareTicker, removeCompareTicker } = useAppStore()
  const [activeMetric, setActiveMetric] = useState(COMPARE_METRICS[0])

  const { data, isLoading, error } = useCompare(compareTickers)

  const colors = Object.fromEntries(
    compareTickers.map((t, i) => [t, TICKER_COLORS[i]])
  )

  return (
    <section id="s-compare" style={{ minHeight: '100vh', padding: '56px 52px' }}>
      <div className="sec-eyebrow">04 · Compare</div>
      <h2 className="sec-title">Side-by-Side <em>Comparison</em></h2>

      <TickerSelector
        tickers={compareTickers}
        onAdd={addCompareTicker}
        onRemove={removeCompareTicker}
      />

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 20 }}>
        {COMPARE_METRICS.map(m => (
          <Pill key={m.key} active={activeMetric.key === m.key} onClick={() => setActiveMetric(m)}>
            {m.label}
          </Pill>
        ))}
      </div>

      {compareTickers.length < 2 && (
        <EmptyState message="Add at least 2 tickers to compare." />
      )}

      {compareTickers.length >= 2 && (
        <>
          {isLoading && <SkeletonCard height={220} />}
          {error && <ErrorCard />}
          {data && (
            <>
              <div className="card" style={{ marginBottom: 18 }}>
                <div style={{ /* legend + label */ }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--muted)', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                    {activeMetric.label} · 10-Year Overlay
                  </span>
                  {/* legend */}
                </div>
                <CompareLineChart
                  data={Object.fromEntries(compareTickers.map(t => [t, data[t]?.fundamentals ?? []]))}
                  metric={activeMetric.key}
                  colors={colors}
                  threshold={activeMetric.threshold}
                  direction={activeMetric.direction}
                  unit={activeMetric.unit}
                />
              </div>

              <ScorecardTable
                tickers={compareTickers}
                data={data}
                colors={colors}
              />
            </>
          )}
        </>
      )}
    </section>
  )
}
```

---

## Verification Checklist

- [ ] `selectedTicker` auto-added to compare tickers on section mount if list is empty
- [ ] `+ Add ticker` shows search dropdown, adds ticker on select
- [ ] Max 5 tickers enforced (add button hidden at 5)
- [ ] Each ticker pill shows correct colour from palette
- [ ] Removing a ticker updates chart and table immediately
- [ ] Metric tab switching changes chart without re-fetching
- [ ] Chart shows correct line per ticker, colour-matched
- [ ] 3rd+ ticker line rendered as dashed
- [ ] Threshold reference line at correct Y position
- [ ] Tooltip shows all ticker values for hovered year
- [ ] Scorecard table shows correct pass/warn/fail per cell
- [ ] Score row shows correct total
- [ ] Row hover effect works in scorecard
- [ ] Empty state shown when fewer than 2 tickers selected
