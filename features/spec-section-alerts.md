# spec-section-alerts.md
# Section 06 — Portfolio Quality Alerts

> **Depends on:** Portfolio section complete, `useHoldings`, `usePortfolioStats`, `useAllocations` all working  
> **Goal:** Auto-generated health alerts derived entirely from already-fetched portfolio data. No additional API calls.  
> **Done when:** All alert conditions evaluate correctly and cards render with correct state colours.

---

## Files to Create

```
src/components/alerts/
├── AlertsSection.jsx
└── AlertCard.jsx
```

No new API calls or hooks required.

---

## Data Sources

All alert data comes from queries already made by the Portfolio section. Use TanStack Query's cache — do not re-fetch.

```js
const { data: holdings }    = useHoldings()      // cached, staleTime: 30s
const { data: stats }       = usePortfolioStats() // cached, staleTime: 30s
const { data: allocations } = useAllocations()    // cached, staleTime: 30s
```

---

## Alert States

| State key | Tag text | Tag colour | Border colour |
|---|---|---|---|
| `ok` | `✓ Healthy` | `var(--teal)` | `rgba(0,212,170,0.16)` |
| `wa` | `⚠ Watch` | `var(--amber)` | `rgba(245,166,35,0.16)` |
| `in` | `◎ Info` | `var(--blue)` | `rgba(77,158,255,0.16)` |

Background tints:
```
ok → rgba(0,212,170,0.04)
wa → rgba(245,166,35,0.04)
in → rgba(77,158,255,0.04)
```

---

## Alert Generation Logic

Call `generateAlerts(holdings, allocations, stats)` from `lib/quality.js`.

Full list of rules:

### ROCE
```js
const allPassRoce = holdings.every(h => h.quality?.roce_ok)
alerts.push(allPassRoce
  ? { state: 'ok', title: 'All holdings pass ROCE threshold',
      desc: `Portfolio avg ROCE well above 10% minimum.` }
  : { state: 'wa', title: 'ROCE concern detected',
      desc: `One or more holdings below 10% ROCE (10yr avg).` }
)
```

### Revenue Growth
```js
const slowRevenue = holdings.filter(h => !h.quality?.revenue_growth_ok)
if (slowRevenue.length === 0) {
  alerts.push({ state: 'ok', title: 'Revenue growth healthy across portfolio',
    desc: 'All holdings averaging >10% revenue growth.' })
} else {
  slowRevenue.forEach(h => alerts.push({
    state: 'wa',
    title: `${h.ticker} revenue growth slowing`,
    desc: `3yr avg below 10% threshold. Monitor next 2 quarters.`
  }))
}
```

### FCF Growth
```js
const slowFcf = holdings.filter(h => !h.quality?.fcf_growth_ok)
if (slowFcf.length === 0) {
  alerts.push({ state: 'ok', title: 'FCF growth strong across holdings',
    desc: 'All holdings averaging >10% FCF growth.' })
} else {
  slowFcf.forEach(h => alerts.push({
    state: 'wa',
    title: `${h.ticker} FCF growth below threshold`,
    desc: `Free cash flow growth averaging under 10% (10yr).`
  }))
}
```

### LT Debt / FCF
```js
const highDebt = holdings.filter(h => !h.quality?.lt_debt_fcf_ok)
if (highDebt.length === 0) {
  alerts.push({ state: 'ok', title: 'Debt levels well-controlled',
    desc: `Portfolio avg LT Debt/FCF comfortably below 4× limit.` })
} else {
  highDebt.forEach(h => alerts.push({
    state: 'wa',
    title: `${h.ticker} debt elevated`,
    desc: `LT Debt/FCF above 4× threshold (10yr avg).`
  }))
}
```

### PEG Ratio
```js
const highPeg = holdings.filter(h => !h.quality?.peg_ok)
if (highPeg.length === 0) {
  alerts.push({ state: 'ok', title: 'PEG ratios remain attractive',
    desc: 'Weighted avg PEG below 2 — portfolio not overvalued on growth basis.' })
} else {
  highPeg.forEach(h => alerts.push({
    state: 'wa',
    title: `${h.ticker} PEG elevated`,
    desc: `PEG above 2 threshold — market may be pricing in too much growth.`
  }))
}
```

### Portfolio Beta
```js
if (stats?.beta != null) {
  if (stats.beta < 0.8) {
    alerts.push({ state: 'in', title: `Portfolio beta: ${stats.beta.toFixed(2)} — defensive`,
      desc: 'Significantly below market. Lower volatility, may lag in strong bull markets.' })
  } else if (stats.beta <= 1.0) {
    alerts.push({ state: 'in', title: `Portfolio beta: ${stats.beta.toFixed(2)}`,
      desc: 'Below market — lower volatility than S&P 500.' })
  } else if (stats.beta <= 1.3) {
    alerts.push({ state: 'in', title: `Portfolio beta: ${stats.beta.toFixed(2)} — near market`,
      desc: 'Near-market volatility. Reasonable for quality equities.' })
  } else {
    alerts.push({ state: 'wa', title: `High beta: ${stats.beta.toFixed(2)}`,
      desc: 'Portfolio more volatile than market. Consider lower-beta additions.' })
  }
}
```

### Geographic Concentration
```js
allocations?.by_country?.forEach(c => {
  if (c.percentage > 60) {
    alerts.push({ state: 'wa',
      title: `${c.label} concentration at ${c.percentage.toFixed(1)}%`,
      desc: 'High geographic concentration. Consider diversifying into other markets.' })
  } else if (c.percentage > 40) {
    alerts.push({ state: 'in',
      title: `${c.label} at ${c.percentage.toFixed(1)}% of portfolio`,
      desc: 'Meaningful single-country exposure. Monitor macro conditions.' })
  }
})
```

### Sector Concentration
```js
allocations?.by_sector?.forEach(s => {
  if (s.percentage > 50) {
    alerts.push({ state: 'wa',
      title: `${s.label} sector at ${s.percentage.toFixed(1)}%`,
      desc: 'High sector concentration risk. Consider diversifying.' })
  }
})
```

### Quality Score Summary
```js
const avgScore = stats?.quality_score_avg
if (avgScore != null) {
  if (avgScore >= 5) {
    alerts.push({ state: 'ok', title: `Portfolio quality score: ${avgScore.toFixed(1)}/6`,
      desc: 'Excellent average quality across holdings.' })
  } else if (avgScore >= 4) {
    alerts.push({ state: 'in', title: `Portfolio quality score: ${avgScore.toFixed(1)}/6`,
      desc: 'Good quality. One or two holdings drag the average slightly.' })
  } else {
    alerts.push({ state: 'wa', title: `Portfolio quality score: ${avgScore.toFixed(1)}/6`,
      desc: 'Below target quality. Review underperforming holdings.' })
  }
}
```

### No Holdings
```js
if (!holdings || holdings.length === 0) {
  alerts.push({ state: 'in', title: 'No holdings in portfolio',
    desc: 'Add holdings in the Portfolio section to see quality alerts.' })
}
```

---

## Ordering
Sort alerts: `wa` first → `ok` second → `in` last. Within each group: order of generation.

---

## Component: `<AlertCard />`

### Props
```js
{
  state: 'ok' | 'wa' | 'in'
  title: string
  desc: string
}
```

### Layout
```
┌──────────────────────────────┐
│ [STATE TAG]                  │
│ Title (13px Syne 600)        │
│ Description (10px mono mid)  │
└──────────────────────────────┘
```

### Styling
```jsx
<div style={{
  borderRadius: 14,
  padding: '22px',
  border: `1px solid ${BORDER_COLORS[state]}`,
  background: BG_COLORS[state],
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
}}>
  <div style={{ fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.18em', textTransform: 'uppercase', fontWeight: 500, color: TAG_COLORS[state] }}>
    {TAG_TEXT[state]}
  </div>
  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', lineHeight: 1.4 }}>
    {title}
  </div>
  <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--mid)', lineHeight: 1.6 }}>
    {desc}
  </div>
</div>
```

### Animation
- Each card fades up on section entry with staggered delay: `animation: fadeUp 0.4s ease both; animation-delay: {i * 60}ms`

---

## Component: `<AlertsSection />`

```jsx
export function AlertsSection() {
  const { data: holdings }    = useHoldings()
  const { data: stats }       = usePortfolioStats()
  const { data: allocations } = useAllocations()

  const alerts = useMemo(
    () => generateAlerts(holdings ?? [], allocations ?? {}, stats ?? {}),
    [holdings, stats, allocations]
  )

  // Sort: wa first, ok second, in last
  const sorted = [
    ...alerts.filter(a => a.state === 'wa'),
    ...alerts.filter(a => a.state === 'ok'),
    ...alerts.filter(a => a.state === 'in'),
  ]

  return (
    <section id="s-alerts" style={{ minHeight: '60vh', padding: '56px 52px' }}>
      <div className="sec-eyebrow">06 · Quality Monitor</div>
      <h2 className="sec-title">Portfolio <em>Health Alerts</em></h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 32 }}>
        {sorted.map((alert, i) => (
          <AlertCard key={i} {...alert} style={{ animationDelay: `${i * 60}ms` }} />
        ))}
      </div>

      <div style={{ textAlign: 'center', padding: '48px 0 24px', fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.22em', color: 'var(--muted)', textTransform: 'uppercase' }}>
        — Alphavault v0.1.0 · Quality Investing Dashboard —
      </div>
    </section>
  )
}
```

---

## Wiring into `App.jsx`

```jsx
import { AlertsSection } from './components/alerts/AlertsSection'
// Replace s-alerts shell:
<AlertsSection />
```

---

## Verification Checklist

- [ ] No additional API calls fired by this section (verify in Network tab)
- [ ] Alerts section uses cached data from Portfolio section queries
- [ ] `wa` alerts appear before `ok` and `in` alerts
- [ ] ROCE alert: `ok` when all holdings pass, `wa` when any fail
- [ ] Individual ticker alerts generated for each failing holding
- [ ] Beta alert matches correct state (low/medium/high thresholds)
- [ ] Country concentration `wa` fires when any country > 60%
- [ ] Country concentration `in` fires when any country 40–60%
- [ ] Sector concentration `wa` fires when any sector > 50%
- [ ] Quality score summary reflects correct state
- [ ] `in` alert shown when portfolio is empty
- [ ] All cards render with correct border and background tint
- [ ] State tags have correct colours and text
- [ ] Cards stagger-animate on section entry
- [ ] Footer line renders at bottom
