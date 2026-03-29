# spec-section-quality.md
# Section 02 — Quality Analysis

> **Depends on:** Search section complete (`selectedTicker` in Zustand store, `useFundamentals` hook working)  
> **Goal:** Full quality scorecard for the selected stock: radar chart, 6 criteria cards, 6 trend charts.  
> **Done when:** Selecting a stock in Search populates all charts in Quality with real data and animations trigger on scroll.

---

## Files to Create

```
src/components/quality/
├── QualitySection.jsx
├── RadarChart.jsx
├── CriteriaGrid.jsx
├── CriterionCard.jsx
└── MiniTrendChart.jsx
```

---

## Data Flow

```
Zustand: selectedTicker
    ↓
useFundamentals(ticker)
    ↓
{ fundamentals: FundamentalOut[], avg_3yr: QualityCriteria, avg_10yr: QualityCriteria }
    ↓
QualitySection distributes to children as props
```

No additional API calls — everything comes from `useFundamentals`.

---

## Window Toggle

Section has a `window` state: `'3yr'` | `'10yr'`, default `'10yr'`.

- Two pill buttons at top: `3yr avg` and `10yr avg`
- Switching re-renders `RadarChart` and `CriteriaGrid` with the corresponding `avg_3yr` or `avg_10yr` data
- `MiniTrendChart` always shows full history regardless of toggle

---

## Component: `<RadarChart />`

### Props
```js
{
  criteria: QualityCriteria   // { roce_ok, revenue_growth_ok, ..., score }
  fundamentals: FundamentalOut[]
}
```

### Implementation: custom SVG (~300×300 viewBox)

**Grid (background):**
- 4 concentric hexagonal polygons (rings at 25%, 50%, 75%, 100% of radius)
- 6 axis lines from centre to each vertex
- All strokes: `var(--border)`, 1px

**Axis vertices** (for 6 axes starting at top, clockwise):
```
ROCE          → top centre       (150, 30)
Revenue Growth → top right        (243, 82)
FCF Growth     → bottom right     (243, 218)
EPS Growth     → bottom centre    (150, 270)
LT Debt/FCF   → bottom left      (57, 218)
PEG Ratio     → top left         (57, 82)
```

**Data polygon:**
- For each metric, compute `ratio = clamp(value / (2 × threshold), 0, 1)`
  - Higher ratio = closer to outer ring
  - For `direction: below` metrics (LT Debt/FCF, PEG): `ratio = clamp(1 - value / (2 × threshold), 0, 1)`
- Interpolate between centre (150,150) and vertex point by `ratio`
- Draw polygon through all 6 computed points
- `fill: url(#radarGradient)` — radial gradient teal 18% opacity to 3%
- `stroke: var(--teal)`, 2px, `stroke-linejoin: round`
- Vertex dots: 4px circles, `fill: var(--teal)`, `filter: drop-shadow(0 0 5px var(--teal))`

**Centre badge:**
- Rounded rect behind text
- `N/6` in DM Mono 17px teal bold
- `QUALITY` in 8px muted

**Animation:**
- On mount: polygon scales from 0 to 1 via CSS `transform: scale()` on the `<g>` wrapper
- Duration: 0.6s ease-out
- Triggered by Intersection Observer (section entry)

**Labels:**
- Each axis labelled in DM Mono 9px `var(--muted)` outside the outer ring

---

## Component: `<CriteriaGrid />`

### Props
```js
{
  criteria: QualityCriteria
  fundamentals: FundamentalOut[]
  window: '3yr' | '10yr'
}
```

### Layout
- 3×2 CSS grid, gap 10px

### Metric value computation
For each criterion, compute average over last `window === '3yr' ? 3 : 10` years:
```js
const recent = fundamentals.slice(-n)
const avg = recent.filter(f => f[key] != null).reduce((s, f) => s + f[key], 0) / count
```
Use `getState(avg, threshold, direction)` from `lib/quality.js` for colour.

---

## Component: `<CriterionCard />`

### Props
```js
{
  label: string
  value: number | null
  threshold: number
  direction: 'above' | 'below'
  unit: string
}
```

### Layout
```
┌─────────────────────────┐
│ LABEL (9px mono muted)  │
│ VALUE (20px mono color) │
│ ▓▓▓▓░░░ progress bar   │
│ threshold text (8px)    │
└─────────────────────────┘
```

### Styling
- Card border: `1px solid rgba(color, 0.20)` where color matches state
- Background: `var(--surface)`
- `border-radius: 12px`, padding 14px

### Progress bar
- Container: `height: 2px`, `background: var(--border)`, `border-radius: 2px`
- Fill width: `clamp(0, (value / (2 × threshold)) × 100, 100)%`
  - For `below` metrics: `clamp(0, (1 - value / (2 × threshold)) × 100, 100)%`
- Fill colour: matches state colour
- Animates from 0 to final width on section entry (Intersection Observer)
- Duration: 0.8s ease-out, staggered by 80ms per card (card index × 80ms)

### Value display
- Format: `+14.8%` for growth rates, `38.2%` for ROCE, `1.8×` for LT Debt/FCF, `1.42` for PEG
- Colour: `var(--teal)` | `var(--amber)` | `var(--red)`
- If `value == null`: show `—` in `var(--muted)`

### Threshold text
- `> 10% threshold ✓` or `< 4× threshold ✓` or `✗`

---

## Component: `<MiniTrendChart />`

### Props
```js
{
  label: string
  data: number[]        // values per year, may contain nulls
  years: number[]       // fiscal years array
  threshold: number
  direction: 'above' | 'below'
  color: string         // CSS variable string e.g. 'var(--teal)'
  currentValue: number | null
}
```

### Layout (per card)
- Container: `var(--card)` background, `var(--border)` border, `border-radius: 12px`
- Height: 148px
- Padding: `16px 18px 12px`
- Content:
  - `label` in 9px DM Mono uppercase muted
  - `currentValue` formatted in 18px DM Mono, coloured by state
  - SVG chart below

### SVG chart
- ViewBox: `0 0 260 70`
- Filter null values before plotting; interpolate gaps
- Dashed threshold line: horizontal, `stroke: var(--muted)`, 1px, `stroke-dasharray: 3 3`
  - Y position: normalised threshold within chart range
  - Label: threshold value in 7px DM Mono
- Line: smooth path through data points, `stroke: {color}`, 2px, `stroke-linecap: round`
- Area fill: gradient from color at 20% opacity to 0%
- Endpoint dot: 3px filled circle, same color, drop-shadow glow

**Draw animation:**
- On Intersection Observer trigger: `stroke-dashoffset` animates 1000 → 0 over 1.2s
- Once triggered, does not re-animate

**6 charts to render (2 rows of 3):**

| Metric key | Label | Color |
|---|---|---|
| `roce` | ROCE % | `var(--teal)` |
| `revenue_growth` | Revenue Growth % | `var(--blue)` |
| `fcf_growth` | FCF Growth % | `var(--purple)` |
| `eps_growth` | EPS Growth % | `var(--amber)` |
| `lt_debt_to_fcf` | LT Debt / FCF | `var(--red)` |
| `peg_ratio` | PEG Ratio | `var(--blue)` |

---

## Component: `<QualitySection />`

```jsx
export function QualitySection() {
  const selectedTicker = useAppStore(s => s.selectedTicker)
  const { data, isLoading, error, refetch } = useFundamentals(selectedTicker)
  const [window, setWindow] = useState('10yr')
  const sectionRef = useRef(null)

  const criteria = window === '3yr' ? data?.avg_3yr : data?.avg_10yr

  return (
    <section id="s-quality" ref={sectionRef} ...>
      <div className="sec-eyebrow">02 · Quality Analysis</div>
      <h2 className="sec-title">
        {selectedTicker ?? '—'} Quality <em>Scorecard</em>
      </h2>

      {/* Window toggle */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 28 }}>
        <Pill active={window === '3yr'}  onClick={() => setWindow('3yr')}>3yr avg</Pill>
        <Pill active={window === '10yr'} onClick={() => setWindow('10yr')}>10yr avg</Pill>
      </div>

      {/* No ticker selected */}
      {!selectedTicker && <EmptyState message="Search for a stock above to see its quality scorecard." />}

      {isLoading && <SkeletonQuality />}
      {error && <ErrorCard onRetry={refetch} />}

      {data && (
        <>
          {/* Row 1: Radar + Criteria grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: 28, marginBottom: 28 }}>
            <RadarChart criteria={criteria} fundamentals={data.fundamentals} />
            <CriteriaGrid criteria={criteria} fundamentals={data.fundamentals} window={window} />
          </div>

          {/* Row 2: 6 mini trend charts */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            {/* first row */}
            <MiniTrendChart label="ROCE %" ... />
            <MiniTrendChart label="Revenue Growth %" ... />
            <MiniTrendChart label="FCF Growth %" ... />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginTop: 12 }}>
            {/* second row */}
            <MiniTrendChart label="EPS Growth %" ... />
            <MiniTrendChart label="LT Debt / FCF" ... />
            <MiniTrendChart label="PEG Ratio" ... />
          </div>
        </>
      )}
    </section>
  )
}
```

### Empty / no ticker state
```jsx
function EmptyState({ message }) {
  return (
    <div className="card" style={{ padding: 48, textAlign: 'center' }}>
      <div style={{ fontFamily: 'var(--mono)', color: 'var(--muted)', fontSize: 12 }}>{message}</div>
    </div>
  )
}
```

### Skeleton state
- Show 1 skeleton card at 360px (radar placeholder) + 6 small skeleton cards in grid

---

## Wiring into `App.jsx`

```jsx
import { QualitySection } from './components/quality/QualitySection'
// Replace s-quality shell:
<QualitySection />
```

---

## Verification Checklist

- [ ] With no stock selected: empty state message shown
- [ ] After searching and selecting MSFT: quality section populates with real data
- [ ] Radar polygon shape matches the 6 criteria values (larger = better)
- [ ] Centre badge shows correct `N/6` score
- [ ] `10yr avg` and `3yr avg` toggle re-renders radar and criteria cards
- [ ] All 6 criterion cards show correct pass/warn/fail colour
- [ ] Progress bars animate on section scroll-into-view, staggered
- [ ] All 6 mini trend charts render with correct colour per metric
- [ ] Threshold dashed lines are at correct Y position on each chart
- [ ] Line draw animation fires on section entry and does not repeat
- [ ] Skeleton shown while loading
- [ ] Error card with retry shown on API failure
