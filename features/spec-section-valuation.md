# spec-section-valuation.md
# Section 03 — Valuation

> **Depends on:** Quality section complete, `useFundamentals` working, `selectedTicker` in store  
> **Goal:** DCF intrinsic value with adjustable inputs + reverse DCF implied growth with sensitivity heatmap.  
> **Done when:** DCF card shows correct intrinsic value for MSFT, inputs update the chart in real time, heatmap highlights current price cell.

---

## Files to Create

```
src/
├── hooks/useDCF.js
└── components/valuation/
    ├── ValuationSection.jsx
    ├── DCFCard.jsx
    ├── DCFWaterfallChart.jsx
    ├── DCFInputs.jsx
    └── ReverseDCFCard.jsx
```

---

## File: `src/hooks/useDCF.js`

```js
import { useQuery } from '@tanstack/react-query'
import { stocksApi } from '../api/stocks'

export function useDCF(ticker, inputs) {
  return useQuery({
    queryKey: ['dcf', ticker, inputs],
    queryFn: () => stocksApi.computeDcf(ticker, inputs),
    enabled: !!ticker,
    staleTime: 0,     // always recompute when inputs change
  })
}

export function useReverseDCF(ticker, params) {
  return useQuery({
    queryKey: ['reverse-dcf', ticker, params],
    queryFn: () => stocksApi.getReverseDcf(ticker, params),
    enabled: !!ticker,
    staleTime: 3_600_000,
  })
}
```

---

## DCF Default Inputs

```js
export const DCF_DEFAULTS = {
  wacc:                 0.10,
  terminal_growth:      0.03,
  fcf_growth_years_1_5: 0.15,
  fcf_growth_years_6_10: 0.08,
  years:                10,
}
```

---

## Component: `<DCFInputs />`

### Props
```js
{
  inputs: DCFInput
  onChange: (inputs: DCFInput) => void
}
```

### UI
- Collapsible `<details>` element, `<summary>` says `Adjust Assumptions ▾`
- Summary styled: DM Mono 10px, `var(--mid)`, cursor pointer, border-bottom `var(--border)`
- Open by default

### 4 sliders:

| Label | Key | Min | Max | Step | Display |
|---|---|---|---|---|---|
| WACC | `wacc` | 0.05 | 0.20 | 0.005 | `10.0%` |
| Terminal Growth | `terminal_growth` | 0.01 | 0.06 | 0.005 | `3.0%` |
| FCF Growth Y1–5 | `fcf_growth_years_1_5` | 0 | 0.40 | 0.01 | `15%` |
| FCF Growth Y6–10 | `fcf_growth_years_6_10` | 0 | 0.30 | 0.01 | `8%` |

Each slider row:
```
LABEL                          VALUE
[══════════════════════○══════]
```
- Label: DM Mono 9px uppercase muted
- Value: DM Mono 13px teal, right-aligned
- Slider: accent colour `var(--teal)`, `background: var(--border)`, height 2px

### Behaviour
- `onChange` called immediately on slider move (no debounce here — `useDCF` query key changes, TanStack Query debounces naturally by render)

---

## Component: `<DCFWaterfallChart />`

### Props
```js
{
  projectedFcfs: Array<{year, fcf, pv, growth_rate}>
  terminalValue: number
  intrinsicValue: number
  currentPrice: number | null
}
```

### SVG chart (viewBox `0 0 400 130`)

**Bars:**
- 10 bars for Y1–Y10, evenly spaced
- Bar height proportional to `pv` value (tallest = Y10)
- Bar colour: `linear-gradient(var(--teal), #008866)`
- Opacity: 0.35 (Y1) → 1.0 (Y10), linear
- Corner radius: 3px

**Terminal value:**
- Stacked on top of Y10 bar in `var(--blue)` at 70% opacity
- Labelled `TV` above in 7px DM Mono blue

**Reference lines (dashed horizontal):**
- Intrinsic value line: `var(--teal)`, dashed, labelled `$487 IV` in teal 10px
- Current price line: `var(--mid)`, dashed, labelled `$421` in mid 10px
- Both right-aligned outside bar area

**Year labels:** beneath each bar in 7.5px DM Mono `var(--muted)`

**Animation:**
- Bars grow from height 0 on Intersection Observer trigger
- Duration: 0.6s ease-out, staggered 60ms per bar

---

## Component: `<DCFCard />`

### Props
```js
{
  ticker: string
}
```

### State
```js
const [inputs, setInputs] = useState(DCF_DEFAULTS)
```

### Data
```js
const { data, isLoading, error, refetch } = useDCF(ticker, inputs)
```

### Layout
```
┌────────────────────────────────────────────┐
│ LABEL: Discounted Cash Flow · 10yr         │
│                                            │
│ $487          $421         $87.6B          │
│ Intrinsic     Market       FCF TTM         │
│ Value         Price                        │
│                                            │
│ [DCFWaterfallChart]                        │
│                                            │
│ ┌── Margin of Safety ──────────── +15.7% ┐ │
│ └─────────────────────────────────────────┘ │
│                                            │
│ [DCFInputs]                                │
└────────────────────────────────────────────┘
```

### Number row
- 3 columns grid
- Intrinsic value: 24px DM Mono `var(--teal)`
- Market price: 24px DM Mono `var(--text)`
- FCF TTM: 16px DM Mono `var(--mid)`, formatted with `fmtLarge`

### Margin of Safety strip
```
background: rgba(0,212,170,0.06)
border: 1px solid rgba(0,212,170,0.14)
border-radius: 10px
padding: 12px 16px
```
- Left: `MARGIN OF SAFETY` label (9px mono muted) + sub-label "Upside to intrinsic value"
- Right: value in 22px DM Mono
  - Positive (undervalued) → `var(--teal)`
  - Negative (overvalued) → `var(--red)`

### Loading: `<SkeletonCard height={400} />`
### Error: `<ErrorCard onRetry={refetch} />`

---

## Component: `<ReverseDCFCard />`

### Props
```js
{
  ticker: string
}
```

### Data
```js
const [params, setParams] = useState({ wacc: 0.10, terminal_growth: 0.03 })
const { data, isLoading, error } = useReverseDCF(ticker, params)
```

### Layout
```
┌────────────────────────────────────────────┐
│ LABEL: Reverse DCF · Implied Growth        │
│                                            │
│ +11.2%                                     │
│ (44px amber mono)                          │
│                                            │
│ Market is pricing in 11.2% annual FCF      │
│ growth. Historical avg: 18.3% — appears    │
│ undervalued.                               │
│                                            │
│ [Sensitivity heatmap SVG]                  │
└────────────────────────────────────────────┘
```

### Implied growth rate
- 44px DM Mono `var(--amber)`
- Sub-label: "implied by market" in 12px muted

### Description text
```
"Market is pricing in {X}% annual FCF growth.
Historical avg: {Y}% — appears [undervalued / overvalued]."
```
- `{X}` = `implied_growth_rate * 100` formatted to 1dp
- `{Y}` = average of last 10yr `fcf_growth` from fundamentals × 100
- "undervalued" in teal if implied < historical, "overvalued" in red if implied > historical

### Sensitivity heatmap (custom SVG, viewBox `0 0 380 88`)

**Data source:** `data.sensitivity` — array of `{growth_rate, implied_price}`

**Cells:** 9 cells evenly spaced (use all sensitivity entries)

Each cell:
- Width: 38px, height: 52px, `border-radius: 4px`
- Background colour: interpolate between `rgba(255,77,106,0.14)` (lowest growth) → `rgba(245,166,35,0.12)` → `rgba(0,212,170,0.34)` (highest growth)
- Text line 1: implied price in 9px DM Mono, coloured to match state
- Text line 2: growth rate % in 8px DM Mono `var(--muted)`

**Highlight rules:**
- Cell whose `implied_price` is closest to `currentPrice`: amber `1px solid var(--amber)` border + amber label text
- Cell whose `growth_rate` is closest to historical FCF avg: teal dashed vertical marker line below cell

**Axis labels:**
- Below cells: `← undervalued · overvalued →` in 8px DM Mono `var(--muted)`
- Amber label "current price" below highlighted cell
- Teal label "hist. avg" below historical marker

### WACC / Terminal Growth mini-adjusters
- Below heatmap: two inline `<select>` dropdowns
  - WACC: 6%, 8%, 10%, 12%, 15% options
  - Terminal Growth: 2%, 3%, 4% options
- On change: update `params`, re-fetches via TanStack Query

---

## Component: `<ValuationSection />`

```jsx
export function ValuationSection() {
  const selectedTicker = useAppStore(s => s.selectedTicker)

  return (
    <section id="s-valuation" style={{ minHeight: '100vh', padding: '56px 52px' }}>
      <div className="sec-eyebrow">03 · Valuation</div>
      <h2 className="sec-title">DCF & Reverse <em>DCF Analysis</em></h2>

      {!selectedTicker && <EmptyState message="Search for a stock above to see valuation analysis." />}

      {selectedTicker && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 22 }}>
          <DCFCard ticker={selectedTicker} />
          <ReverseDCFCard ticker={selectedTicker} />
        </div>
      )}
    </section>
  )
}
```

---

## Verification Checklist

- [ ] DCF card shows intrinsic value, market price, FCF TTM for MSFT
- [ ] Waterfall bars grow on scroll-into-view, staggered correctly
- [ ] Terminal value bar stacked on Y10 in blue
- [ ] Intrinsic value + current price reference lines visible and labelled
- [ ] Margin of safety is green when positive, red when negative
- [ ] `Adjust Assumptions` expander opens 4 sliders
- [ ] Moving a slider updates the DCF chart and intrinsic value
- [ ] Reverse DCF implied growth rate is displayed in amber
- [ ] Description sentence correctly identifies under/overvalued
- [ ] Heatmap renders 9 cells with correct colour gradient
- [ ] Current price cell highlighted with amber border
- [ ] Historical avg FCF growth marked with teal dashed line
- [ ] Changing WACC dropdown re-fetches reverse DCF
- [ ] Empty state shown when no ticker selected
- [ ] Skeletons shown during loading
