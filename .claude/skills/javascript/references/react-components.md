# React Component Patterns

## Server vs Client Components

**Server Components (default in Next.js)**
- Run on the server. No hooks, no event handlers, no browser APIs.
- Use for: data fetching, rendering static content, reducing bundle size.

**Client Components (`'use client'`)**
- Enable: hooks, state, effects, event handlers, browser APIs.
- Add `'use client'` to the **leaf component** — never to a parent layout.

```jsx
// ❌ Bad — disables RSC for entire subtree
'use client'
export default function WarehousesLayout({ children }) { ... }

// ✅ Good — only the interactive leaf is a client component
'use client'
export function UpdateStockButton({ warehouseId }) {
  const [updated, setUpdated] = useState(false)
  return <button onClick={() => setUpdated(true)}>{updated ? 'Updated' : 'Update'}</button>
}
```

## Hook Rules

**useState** — use functional update when next state depends on previous:
```js
setCount((prev) => prev + 1)  // correct
setCount(count + 1)           // stale closure risk in async contexts
```

**useEffect** — only for browser side effects after render. **Never for data fetching** — use TanStack Query instead.

```jsx
useEffect(() => {
  const sub = subscribe(id)
  return () => sub.unsubscribe()
}, [id])
```

**useCallback / useMemo** — only memoize when there is a measurable re-render problem. React Compiler (2025) handles most cases automatically. Skip for simple values and handlers not passed as props.

**useReducer** — for state with multiple interdependent transitions:

```jsx
function reducer(state, action) {
  switch (action.type) {
    case 'increment': return { count: state.count + 1 }
    case 'reset':     return { count: action.payload }
    default:          return state
  }
}
const [state, dispatch] = useReducer(reducer, { count: 0 })
```

**useContext** — only for stable, infrequently-changing values (theme, locale, auth identity). For mutable shared state, use Zustand.

**React 19**: `use(Context)` replaces `useContext` and can be called conditionally.

## Custom Hooks

Extract component logic into reusable hooks. Prefix with `use`. Return `[value, setter]` tuple for simple state; `{ data, error, isLoading }` object for complex.

```js
export function useLocalStorage(key, initial) {
  const [value, setValue] = useState(() => {
    const stored = localStorage.getItem(key)
    return stored ? JSON.parse(stored) : initial
  })

  const set = useCallback((next) => {
    setValue(next)
    localStorage.setItem(key, JSON.stringify(next))
  }, [key])

  return [value, set]
}
```

## Compound Component Pattern

Share state internally via Context. Expose subcomponents as properties of the parent.

```jsx
const TabsContext = createContext(null)

function useTabs() {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error('Must be used inside <Tabs>')
  return ctx
}

export function Tabs({ children, defaultTab }) {
  const [activeTab, setActiveTab] = useState(defaultTab)
  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      {children}
    </TabsContext.Provider>
  )
}

Tabs.Tab = function Tab({ id, children }) {
  const { setActiveTab } = useTabs()
  return <button onClick={() => setActiveTab(id)}>{children}</button>
}

Tabs.Panel = function Panel({ id, children }) {
  const { activeTab } = useTabs()
  return activeTab === id ? <div>{children}</div> : null
}
```

## Suspense and Error Boundaries

Wrap async Server Components in `<Suspense>` at the data boundary. Wrap feature areas in `<ErrorBoundary>` — use `react-error-boundary` library.

```jsx
import { ErrorBoundary } from 'react-error-boundary'

<ErrorBoundary fallback={<WarehouseError />}>
  <Suspense fallback={<Skeleton />}>
    <WarehouseList />
  </Suspense>
</ErrorBoundary>
```

`loading.js` in a Next.js route folder automatically wraps the page in `<Suspense>`.

## Performance

**React.memo** — only for components that render frequently with unchanged props:
```jsx
const WarehouseCard = memo(function WarehouseCard({ id, name, capacity }) { ... })
```

**Virtualization** — use `@tanstack/react-virtual` for lists over 50–100 items:
```jsx
const virtualizer = useVirtualizer({
  count: items.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 72,
})
```

**Code splitting** — use `next/dynamic` for heavy components not needed on initial render:
```jsx
const HeavyChart = dynamic(() => import('@/components/HeavyChart'), {
  loading: () => <ChartSkeleton />,
  ssr: false,
})
```
