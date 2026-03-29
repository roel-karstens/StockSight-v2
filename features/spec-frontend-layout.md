# spec-frontend-layout.md
# Frontend Scaffold & Layout

> **Phase:** 3 — React scaffold, global layout, design system  
> **Depends on:** Backend API running at `http://localhost:8000`  
> **Goal:** Vite + React + Tailwind running with sidebar, scroll container, progress bar, and empty section shells. No data fetching yet.  
> **Done when:** `npm run dev` shows the full-page layout with working scroll, animated progress bar, and active sidebar state.

---

## Package Setup

### `package.json` dependencies
```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "axios": "^1.7.0",
    "recharts": "^2.12.0",
    "@tanstack/react-query": "^5.40.0",
    "zustand": "^4.5.0",
    "lucide-react": "^0.383.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.2.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }
}
```

### `vite.config.js`
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

### `tailwind.config.js`
```js
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg:      '#07080D',
        surface: '#0C0E15',
        card:    '#10131C',
        border:  '#1A1F2E',
        border2: '#232840',
        teal:    '#00D4AA',
        amber:   '#F5A623',
        red:     '#FF4D6A',
        blue:    '#4D9EFF',
        purple:  '#A78BFA',
        mid:     '#7A859E',
        muted:   '#3D4560',
      },
      fontFamily: {
        sans: ['Syne', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
      },
    },
  },
}
```

---

## File: `src/styles/globals.css`

```css
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=Syne:wght@400;600;700;800&display=swap');
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg:         #07080D;
  --surface:    #0C0E15;
  --card:       #10131C;
  --border:     #1A1F2E;
  --border2:    #232840;
  --teal:       #00D4AA;
  --teal-dim:   rgba(0, 212, 170, 0.10);
  --teal-glow:  0 0 24px rgba(0, 212, 170, 0.35);
  --amber:      #F5A623;
  --red:        #FF4D6A;
  --blue:       #4D9EFF;
  --purple:     #A78BFA;
  --text:       #DDE3F0;
  --mid:        #7A859E;
  --muted:      #3D4560;
  --mono:       'DM Mono', monospace;
  --sans:       'Syne', sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #root { height: 100%; overflow: hidden; }
body { background: var(--bg); color: var(--text); font-family: var(--sans); }

/* Scrollbar */
.scroll-area::-webkit-scrollbar       { width: 4px; }
.scroll-area::-webkit-scrollbar-track { background: transparent; }
.scroll-area::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

/* Section eyebrow */
.sec-eyebrow {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.22em;
  color: var(--muted);
  text-transform: uppercase;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.sec-eyebrow::before {
  content: '';
  display: inline-block;
  width: 18px;
  height: 1px;
  background: var(--muted);
}

/* Section title */
.sec-title {
  font-size: clamp(28px, 3.5vw, 48px);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.0;
  margin-bottom: 36px;
}
.sec-title em {
  font-style: normal;
  color: var(--teal);
}

/* Card base */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px;
}

/* Chip / tag */
.tag {
  padding: 3px 9px;
  border-radius: 20px;
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.06em;
  border: 1px solid;
}

/* Skeleton shimmer */
@keyframes shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
.skeleton {
  background: linear-gradient(90deg, var(--border) 25%, var(--border2) 50%, var(--border) 75%);
  background-size: 800px 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;
}

/* Animations */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}
@keyframes bob {
  0%, 100% { transform: translateY(0); }
  50%       { transform: translateY(5px); }
}
@keyframes drawLine {
  from { stroke-dashoffset: 1000; }
  to   { stroke-dashoffset: 0; }
}

.animate-fade-up   { animation: fadeUp 0.4s ease both; }
.animate-pulse-dot { animation: pulse 2s infinite; }
.animate-bob       { animation: bob 1.8s ease-in-out infinite; }
.draw-line         { animation: drawLine 1.2s ease-out both; stroke-dasharray: 1000; }
```

---

## File: `src/api/client.js`

```js
import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL + '/api/v1',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    console.error('[API Error]', err.response?.status, err.response?.data)
    return Promise.reject(err)
  }
)
```

---

## File: `src/store/useAppStore.js`

```js
import { create } from 'zustand'

export const useAppStore = create((set) => ({
  // Currently viewed stock ticker
  selectedTicker: null,
  setSelectedTicker: (ticker) => set({ selectedTicker: ticker }),

  // Tickers loaded in compare section
  compareTickers: [],
  addCompareTicker: (ticker) =>
    set((s) => ({
      compareTickers: s.compareTickers.includes(ticker) || s.compareTickers.length >= 5
        ? s.compareTickers
        : [...s.compareTickers, ticker],
    })),
  removeCompareTicker: (ticker) =>
    set((s) => ({ compareTickers: s.compareTickers.filter((t) => t !== ticker) })),

  // Active scroll section (for sidebar highlight)
  activeSection: 's-search',
  setActiveSection: (id) => set({ activeSection: id }),
}))
```

---

## File: `src/hooks/useScrollSpy.js`

```js
import { useEffect } from 'react'
import { useAppStore } from '../store/useAppStore'

const SECTION_IDS = [
  's-search', 's-quality', 's-valuation',
  's-compare', 's-portfolio', 's-alerts',
]

export function useScrollSpy(scrollRef) {
  const setActiveSection = useAppStore((s) => s.setActiveSection)

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActiveSection(entry.target.id)
        })
      },
      {
        root: scrollRef.current,
        threshold: 0.3,
      }
    )

    SECTION_IDS.forEach((id) => {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [scrollRef, setActiveSection])
}
```

---

## File: `src/components/layout/ProgressBar.jsx`

```jsx
import { useEffect, useRef } from 'react'

export function ProgressBar({ scrollRef }) {
  const barRef = useRef(null)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    const onScroll = () => {
      const pct = el.scrollTop / (el.scrollHeight - el.clientHeight) * 100
      if (barRef.current) barRef.current.style.width = Math.min(pct, 100) + '%'
    }

    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [scrollRef])

  return (
    <div className="sticky top-0 left-0 right-0 h-[2px] bg-border z-50">
      <div
        ref={barRef}
        className="h-full w-0 transition-[width] duration-[80ms] linear"
        style={{
          background: 'linear-gradient(90deg, #00D4AA, #4D9EFF)',
          boxShadow: '0 0 10px rgba(0, 212, 170, 0.5)',
        }}
      />
    </div>
  )
}
```

---

## File: `src/components/layout/Sidebar.jsx`

```jsx
import { useAppStore } from '../../store/useAppStore'

const NAV_ITEMS = [
  { id: 's-search',    icon: '⌕', label: 'Search'    },
  { id: 's-quality',   icon: '◈', label: 'Quality'   },
  { id: 's-valuation', icon: '◎', label: 'Value'     },
  { id: 's-compare',   icon: '⊞', label: 'Compare'   },
  null, // separator
  { id: 's-portfolio', icon: '◫', label: 'Portfolio' },
  { id: 's-alerts',    icon: '◬', label: 'Alerts'    },
]

export function Sidebar({ scrollRef }) {
  const activeSection = useAppStore((s) => s.activeSection)

  const goTo = (id) => {
    const el = document.getElementById(id)
    if (el && scrollRef.current) {
      scrollRef.current.scrollTo({ top: el.offsetTop, behavior: 'smooth' })
    }
  }

  return (
    <nav
      className="flex flex-col items-center gap-1 flex-shrink-0 z-50"
      style={{
        width: 68,
        background: 'var(--surface)',
        borderRight: '1px solid var(--border)',
        padding: '18px 0 24px',
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center justify-center text-xl mb-6 cursor-pointer"
        style={{
          width: 38, height: 38,
          background: 'linear-gradient(135deg, #00D4AA, #0066FF)',
          borderRadius: 11,
          boxShadow: 'var(--teal-glow)',
        }}
      >
        ⬡
      </div>

      {NAV_ITEMS.map((item, i) => {
        if (!item) return (
          <div key={i} style={{ width: 28, height: 1, background: 'var(--border)', margin: '8px 0' }} />
        )
        const isActive = activeSection === item.id
        return (
          <button
            key={item.id}
            onClick={() => goTo(item.id)}
            className="flex flex-col items-center justify-center gap-[2px] rounded-xl transition-all duration-[180ms] border-none cursor-pointer relative"
            style={{
              width: 46, height: 46,
              background: isActive ? 'var(--teal-dim)' : 'transparent',
              color: isActive ? 'var(--teal)' : 'var(--muted)',
            }}
          >
            {isActive && (
              <div
                className="absolute left-0 top-1/2 -translate-y-1/2 rounded-r-sm"
                style={{ width: 2, height: 22, background: 'var(--teal)', left: -1, boxShadow: 'var(--teal-glow)' }}
              />
            )}
            <span style={{ fontSize: 17, lineHeight: 1 }}>{item.icon}</span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 8, letterSpacing: '0.06em' }}>{item.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
```

---

## File: `src/components/ui/Skeleton.jsx`

```jsx
export function Skeleton({ className = '', style = {} }) {
  return <div className={`skeleton ${className}`} style={style} />
}

export function SkeletonCard({ height = 200 }) {
  return (
    <div className="card" style={{ height }}>
      <Skeleton style={{ height: 12, width: '40%', marginBottom: 16 }} />
      <Skeleton style={{ height: 32, width: '60%', marginBottom: 12 }} />
      <Skeleton style={{ height: height - 80 }} />
    </div>
  )
}
```

---

## File: `src/components/ui/ErrorCard.jsx`

```jsx
export function ErrorCard({ message = 'Something went wrong', onRetry }) {
  return (
    <div className="card" style={{ border: '1px solid var(--red)', textAlign: 'center', padding: 32 }}>
      <div style={{ color: 'var(--red)', fontFamily: 'var(--mono)', fontSize: 11, marginBottom: 8 }}>
        ✕ Error
      </div>
      <div style={{ color: 'var(--mid)', fontFamily: 'var(--mono)', fontSize: 12, marginBottom: 16 }}>
        {message}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            padding: '6px 16px', borderRadius: 8,
            border: '1px solid var(--border2)',
            background: 'transparent', color: 'var(--text)',
            fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer',
          }}
        >
          Retry
        </button>
      )}
    </div>
  )
}
```

---

## File: `src/components/ui/Pill.jsx`

```jsx
export function Pill({ children, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '5px 13px',
        borderRadius: 20,
        fontFamily: 'var(--mono)',
        fontSize: 9,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        cursor: 'pointer',
        border: `1px solid ${active ? 'rgba(0,212,170,0.3)' : 'var(--border)'}`,
        background: active ? 'var(--teal-dim)' : 'transparent',
        color: active ? 'var(--teal)' : 'var(--muted)',
        transition: 'all 0.14s',
      }}
    >
      {children}
    </button>
  )
}
```

---

## File: `src/lib/formatters.js`

```js
export const fmtCurrency = (v) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: 2,
  }).format(v)

export const fmtPct = (v, alreadyPercent = false) => {
  const val = alreadyPercent ? v : v * 100
  return `${val > 0 ? '+' : ''}${val.toFixed(1)}%`
}

export const fmtLarge = (v) =>
  v >= 1e12 ? `$${(v / 1e12).toFixed(1)}T`
  : v >= 1e9  ? `$${(v / 1e9).toFixed(1)}B`
  : v >= 1e6  ? `$${(v / 1e6).toFixed(0)}M`
  : `$${v.toFixed(0)}`

export const fmtMultiple = (v) => `${v.toFixed(1)}×`

export const fmtDate = (d) =>
  new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
```

---

## File: `src/lib/quality.js`

```js
export const CRITERIA = [
  { key: 'roce',           label: 'ROCE',           threshold: 10,   direction: 'above', unit: '%' },
  { key: 'revenue_growth', label: 'Revenue Growth', threshold: 0.10, direction: 'above', unit: '%' },
  { key: 'fcf_growth',     label: 'FCF Growth',     threshold: 0.10, direction: 'above', unit: '%' },
  { key: 'eps_growth',     label: 'EPS Growth',     threshold: 0.10, direction: 'above', unit: '%' },
  { key: 'lt_debt_to_fcf', label: 'LT Debt / FCF', threshold: 4,    direction: 'below', unit: '×' },
  { key: 'peg_ratio',      label: 'PEG Ratio',      threshold: 2,    direction: 'below', unit: ''  },
]

// Returns 'pass' | 'warn' | 'fail'
export function getState(value, threshold, direction) {
  if (value == null) return 'fail'
  const margin = threshold * 0.20
  if (direction === 'above') {
    if (value >= threshold)          return 'pass'
    if (value >= threshold - margin) return 'warn'
    return 'fail'
  } else {
    if (value <= threshold)          return 'pass'
    if (value <= threshold + margin) return 'warn'
    return 'fail'
  }
}

export const STATE_COLORS = {
  pass: 'var(--teal)',
  warn: 'var(--amber)',
  fail: 'var(--red)',
}

// Generate alert objects from portfolio data
export function generateAlerts(holdings = [], allocations = {}, stats = {}) {
  const alerts = []

  // ROCE
  const allPassRoce = holdings.every(h => (h.avg_10yr?.roce_ok ?? false))
  alerts.push(allPassRoce
    ? { state: 'ok', title: 'All holdings pass ROCE threshold', desc: `Portfolio weighted avg ROCE exceeds 10% minimum.` }
    : { state: 'wa', title: 'ROCE concern detected', desc: `One or more holdings below 10% ROCE threshold.` }
  )

  // Beta
  if (stats.beta != null) {
    alerts.push(stats.beta < 1
      ? { state: 'in', title: `Portfolio beta: ${stats.beta.toFixed(2)}`, desc: 'Below market — lower volatility than S&P 500.' }
      : stats.beta > 1.3
        ? { state: 'wa', title: `High beta: ${stats.beta.toFixed(2)}`, desc: 'Portfolio more volatile than market.' }
        : { state: 'ok', title: `Portfolio beta: ${stats.beta.toFixed(2)}`, desc: 'Near-market volatility profile.' }
    )
  }

  // Country concentration
  if (allocations.by_country) {
    allocations.by_country.forEach(c => {
      if (c.percentage > 50) {
        alerts.push({ state: 'wa', title: `${c.label} concentration at ${c.percentage.toFixed(1)}%`, desc: 'Geographic concentration risk — consider diversifying.' })
      }
    })
  }

  return alerts
}
```

---

## File: `src/App.jsx`

```jsx
import { useRef } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './components/layout/Sidebar'
import { ProgressBar } from './components/layout/ProgressBar'
import { useScrollSpy } from './hooks/useScrollSpy'
import '../src/styles/globals.css'

// Section placeholders (replaced one by one per sprint)
const SectionShell = ({ id, number, name }) => (
  <section
    id={id}
    style={{ minHeight: '100vh', padding: '56px 52px', borderBottom: '1px solid var(--border)' }}
  >
    <div className="sec-eyebrow">{number} · {name}</div>
    <h2 className="sec-title">{name} <em>Section</em></h2>
    <div className="card" style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ fontFamily: 'var(--mono)', color: 'var(--muted)', fontSize: 12 }}>
        — {name} content coming soon —
      </span>
    </div>
  </section>
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

export default function App() {
  const scrollRef = useRef(null)
  useScrollSpy(scrollRef)

  return (
    <QueryClientProvider client={queryClient}>
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        <Sidebar scrollRef={scrollRef} />
        <main
          ref={scrollRef}
          className="scroll-area"
          style={{ flex: 1, overflowY: 'scroll', position: 'relative' }}
        >
          <ProgressBar scrollRef={scrollRef} />

          {/* Sections — swap shells with real components sprint by sprint */}
          <SectionShell id="s-search"    number="01" name="Search"    />
          <SectionShell id="s-quality"   number="02" name="Quality"   />
          <SectionShell id="s-valuation" number="03" name="Valuation" />
          <SectionShell id="s-compare"   number="04" name="Compare"   />
          <SectionShell id="s-portfolio" number="05" name="Portfolio" />
          <SectionShell id="s-alerts"    number="06" name="Alerts"    />
        </main>
      </div>
    </QueryClientProvider>
  )
}
```

---

## Verification Checklist

- [ ] `npm run dev` starts without errors on port 3000
- [ ] All 6 section shells render and are scrollable
- [ ] Progress bar fills accurately as you scroll
- [ ] Sidebar nav buttons scroll to correct section on click
- [ ] Correct nav button highlights as each section enters viewport
- [ ] Sidebar separator renders between Compare and Portfolio
- [ ] Logo renders with teal/blue gradient
- [ ] Fonts load correctly (DM Mono + Syne visible)
- [ ] Design tokens available as CSS variables
- [ ] `useAppStore` reactive: activeSection updates on scroll
- [ ] `api/client.js` exported and importable (no runtime errors)
- [ ] No TypeScript errors / ESLint warnings on core layout files
