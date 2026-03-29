# spec-section-search.md
# Section 01 — Search

> **Depends on:** `spec-frontend-layout.md` complete  
> **Goal:** User can search a ticker and see a rich stock card with sparkline and quality badge.  
> **Done when:** Typing "MSFT" shows the result card with real data, sparkline draws on appear, quality score is correct.

---

## Files to Create

```
src/
├── api/stocks.js
├── hooks/useFundamentals.js
├── hooks/usePriceHistory.js
└── components/search/
    ├── SearchSection.jsx      # section wrapper
    ├── SearchBar.jsx
    └── StockResultCard.jsx
```

---

## File: `src/api/stocks.js`

```js
import { api } from './client'

export const stocksApi = {
  search:        (q)                    => api.get(`/stocks/search?q=${q}`),
  getStock:      (ticker)               => api.get(`/stocks/${ticker}`),
  getFundamentals: (ticker)             => api.get(`/stocks/${ticker}/fundamentals`),
  getPrices:     (ticker, period='10y') => api.get(`/stocks/${ticker}/prices?period=${period}`),
  compare:       (tickers)              => api.get(`/stocks/compare?tickers=${tickers.join(',')}`),
  computeDcf:    (ticker, inputs)       => api.post(`/stocks/${ticker}/dcf`, inputs),
  getReverseDcf: (ticker, params)       => api.get(`/stocks/${ticker}/reverse-dcf`, { params }),
}
```

---

## File: `src/hooks/useFundamentals.js`

```js
import { useQuery } from '@tanstack/react-query'
import { stocksApi } from '../api/stocks'

export function useFundamentals(ticker) {
  return useQuery({
    queryKey: ['fundamentals', ticker],
    queryFn: () => stocksApi.getFundamentals(ticker),
    enabled: !!ticker,
    staleTime: 86_400_000,   // 24h — matches backend Redis TTL
  })
}
```

---

## File: `src/hooks/usePriceHistory.js`

```js
import { useQuery } from '@tanstack/react-query'
import { stocksApi } from '../api/stocks'

export function usePriceHistory(ticker, period = '10y') {
  return useQuery({
    queryKey: ['prices', ticker, period],
    queryFn: () => stocksApi.getPrices(ticker, period),
    enabled: !!ticker,
    staleTime: 3_600_000,    // 1h — matches backend Redis TTL
  })
}
```

---

## Component: `<SearchBar />`

### Props
```js
{
  onSelect: (ticker: string) => void   // called when user confirms a ticker
}
```

### Behaviour
- Controlled input, value starts empty
- On change: debounce 300ms → call `stocksApi.search(query)` → show dropdown
- Dropdown: list of up to 8 `StockSearchResult` items
  - Each row: ticker (teal mono) · name (muted) · quality badge (`N/6`)
  - Hover: row background lightens
  - Click: calls `onSelect(ticker)`, closes dropdown, sets input value to ticker
- Keyboard:
  - `↓` / `↑` navigate dropdown
  - `Enter` selects highlighted item
  - `Escape` closes dropdown, clears input
- While fetching: subtle spinner in right side of input
- No results: `"No results for '{query}'"` in muted mono text

### Layout
```
┌────────────────────────────────────────────┐
│ ⌕  [input text]                      ⌘K  │
└────────────────────────────────────────────┘
  ┌──────────────────────────────────────┐
  │ MSFT  Microsoft Corporation     6/6  │
  │ MSTR  MicroStrategy Inc.        2/6  │
  └──────────────────────────────────────┘
```

### Styling
- Max-width: 580px
- Input: `background: var(--card)`, `border: 1px solid var(--border2)`, `border-radius: 14px`
- Input padding: `17px 56px` (space for icon left, hint right)
- Font: DM Mono 15px, letter-spacing 0.03em
- Focus: `border-color: var(--teal)`, `box-shadow: 0 0 0 3px var(--teal-dim)`
- Dropdown: same width as input, `background: var(--surface)`, `border: 1px solid var(--border2)`, `border-radius: 12px`, `margin-top: 6px`, `z-index: 20`
- `⌘K` badge: `background: var(--bg)`, `border: 1px solid var(--border)`, `border-radius: 6px`, `padding: 3px 8px`, DM Mono 10px muted

---

## Component: `<StockResultCard />`

### Props
```js
{
  ticker: string
}
```

### Data fetching
- Calls `useFundamentals(ticker)` for quality criteria + name
- Calls `usePriceHistory(ticker, '10y')` for sparkline + current price

### Appearance on mount
- Slides up and fades in: `animation: fadeUp 0.4s ease both`
- Top edge: 1px line `linear-gradient(90deg, transparent, var(--teal), transparent)`

### Layout
```
┌─ top edge gradient ──────────────────────────────┐
│  [Avatar]  [Info col]              [Price col]   │
│            MSFT                    $421.50        │
│            Microsoft Corporation   ▲ +1.24%       │
│            [Tech] [USA] [Mega Cap] ◉ Quality 6/6  │
├──────────────────────────────────────────────────┤
│  [Sparkline SVG — full width, 52px tall]         │
└──────────────────────────────────────────────────┘
```

### Avatar
- 50×50px, `background: linear-gradient(135deg, #0d1e38, #091a2e)`, `border-radius: 12px`
- Shows first 2 chars of ticker in teal DM Mono 13px

### Info column
- Ticker: DM Mono 19px teal, letter-spacing 0.06em
- Company name: DM Mono 300 12px `var(--mid)`
- Tag chips (see below)

### Tag chips
```
Sector  → color: #6B8BC4, border: #1E2D4A, bg: rgba(59,99,200,0.07)
Country → color: #5CC4B8, border: #1C3530, bg: rgba(0,160,150,0.07)
Cap     → color: #9B8FC4, border: #2A253A, bg: rgba(100,80,180,0.07)
```

### Price column (right-aligned)
- Current price: DM Mono 26px `var(--text)`
- Day change: DM Mono 11px, teal if positive, red if negative (from price history last 2 points)
- Quality badge:
  ```
  [pulsing dot] Quality N/6
  background: rgba(0,212,170,0.08)
  border: 1px solid rgba(0,212,170,0.22)
  border-radius: 7px, padding: 5px 10px
  ```

### Sparkline SVG
- Full width, 52px tall, `overflow: visible`
- Data: `prices` array, use `adj_close` values
- X: evenly spaced points
- Y: normalised to [4px, 48px] range
- Teal line, 1.8px stroke, `stroke-linecap: round`
- Area fill: `linearGradient` teal 25% opacity → 0%
- Draw animation: `stroke-dasharray: 1000`, `stroke-dashoffset` animates from 1000→0 over 1.2s on mount
- Endpoint dot: 3.5px filled teal circle with `drop-shadow(0 0 4px var(--teal))`
- Year labels at 25% intervals along bottom in `var(--muted)` 8px DM Mono

### Loading state
- Show skeleton card (same dimensions) while either query is loading

### Error state
- Show `<ErrorCard message="Could not load stock data" onRetry={refetch} />`

---

## Component: `<SearchSection />`

### Behaviour
- Manages `selectedTicker` state (also writes to Zustand store via `setSelectedTicker`)
- When ticker selected: fetches data, renders `<StockResultCard ticker={selectedTicker} />`
- Initially: no result card shown

### Background
- `radial-gradient(ellipse 70% 60% at 60% -10%, rgba(0,212,170,0.06) 0%, transparent 60%)`
- CSS grid overlay: `background-image: linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)`, `background-size: 48px 48px`, `opacity: 0.35`, `mask-image: radial-gradient(ellipse 80% 80% at 50% 50%, black 30%, transparent 80%)`

### Hero text
```
[pulsing dot]  Quality Investing · Alphavault    ← tag pill

Find stocks                                       ← h1 (Syne 800, clamp 44px–80px)
worth owning.                                       (second line in teal)

Quality metrics · DCF analysis · Portfolio        ← DM Mono 300 13px --mid
intelligence
```

### Scroll cue
- Bottom-left of section
- DM Mono 9px muted uppercase: `↓ SCROLL TO ANALYSE`
- Arrow bounces with `animate-bob`

### Full JSX structure
```jsx
<section id="s-search" style={{ minHeight: '100vh', padding: '56px 52px', position: 'relative', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
  {/* background effects */}
  <div className="hero-tag">...</div>
  <h1 className="hero-h1">Find stocks<span>worth owning.</span></h1>
  <p className="hero-sub">...</p>
  <SearchBar onSelect={handleSelect} />
  {selectedTicker && <StockResultCard ticker={selectedTicker} />}
  <div className="scroll-cue">...</div>
</section>
```

---

## Wiring into `App.jsx`

Replace the `s-search` shell:
```jsx
import { SearchSection } from './components/search/SearchSection'
// ...
<SearchSection />
```

---

## Verification Checklist

- [ ] Typing "MSFT" shows dropdown with search results after 300ms debounce
- [ ] Clicking a result sets input value and closes dropdown
- [ ] `StockResultCard` appears with `fadeUp` animation
- [ ] Sparkline draws from left to right on card appear
- [ ] Quality badge shows correct score (e.g. "6/6" for MSFT)
- [ ] Day change is green for positive, red for negative
- [ ] Tag chips show correct sector, country, cap size
- [ ] Skeleton shown while loading
- [ ] Error card shown if API returns error
- [ ] `⌘K` badge visible in search input
- [ ] `Escape` key clears and closes dropdown
- [ ] `selectedTicker` written to Zustand store (check with React DevTools)
