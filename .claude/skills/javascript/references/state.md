# State Management

Zustand for client state. TanStack Query (React Query) for server state.

## When to Use What

| State Type | Tool |
|---|---|
| Server-fetched data (lists, entities) | TanStack Query |
| Form values, UI toggles, local interaction | `useState` / `useReducer` |
| Shared UI state across unrelated components | Zustand |
| Infrequently-changing global config (theme, locale) | React Context |

**Never use** Zustand for data that lives on the server — that's TanStack Query's job.  
**Never use** TanStack Query for purely local UI state.

---

## Zustand

Small, hook-based store. No Provider required.

### Basic Store

```js
// stores/warehouseStore.js
import { create } from 'zustand'
import { devtools } from 'zustand/middleware'

export const useWarehouseStore = create(
  devtools(
    (set) => ({
      selectedIds: [],
      selectWarehouse: (id) =>
        set((s) => ({ selectedIds: [...s.selectedIds, id] })),
      deselectWarehouse: (id) =>
        set((s) => ({ selectedIds: s.selectedIds.filter((x) => x !== id) })),
      clearSelection: () => set({ selectedIds: [] }),
    }),
    { name: 'WarehouseStore' }
  )
)
```

### Selective Access

```jsx
// ✅ Re-renders only when selectedIds changes
const selectedIds = useWarehouseStore((s) => s.selectedIds)

// ❌ Re-renders on any store change
const store = useWarehouseStore()
```

Always use a selector function. Never destructure the whole store.

### Slices Pattern (Large Stores)

```js
// stores/slices/shipmentSlice.js
export const createShipmentSlice = (set) => ({
  activeShipmentId: null,
  setActiveShipment: (id) => set({ activeShipmentId: id }),
})

// stores/appStore.js
import { create } from 'zustand'
import { createShipmentSlice } from './slices/shipmentSlice'
import { createUserSlice } from './slices/userSlice'

export const useAppStore = create((...args) => ({
  ...createShipmentSlice(...args),
  ...createUserSlice(...args),
}))
```

### Persistence

```js
import { persist } from 'zustand/middleware'

export const useSettingsStore = create(
  persist(
    (set) => ({
      theme: 'light',
      setTheme: (theme) => set({ theme }),
    }),
    { name: 'Warehouse-settings' }
  )
)
```

### Rules

- Keep stores small and domain-specific. Multiple small stores > one large store.
- Never store server-fetched data in Zustand — use TanStack Query.
- Actions live inside the store definition, not in components.
- Use `devtools` middleware for Redux DevTools visibility.

---

## TanStack Query

Manages server state: fetching, caching, synchronization, and invalidation.

### Setup

```jsx
// app/providers.js
'use client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useState } from 'react'

export function Providers({ children }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: { staleTime: 60 * 1000 },
    },
  }))

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools />
    </QueryClientProvider>
  )
}
```

### Query Keys

Use hierarchical arrays. Define a factory to avoid string drift.

```js
// lib/queryKeys.js
export const warehouseKeys = {
  all: ['warehouses'],
  list: (filters) => [...warehouseKeys.all, filters],
  detail: (id) => ['warehouse', id],
}
```

### useQuery

```jsx
import { useQuery } from '@tanstack/react-query'

export function useWarehouses(filters) {
  return useQuery({
    queryKey: warehouseKeys.list(filters),
    queryFn: () => fetchWarehouses(filters),
    staleTime: 5 * 60 * 1000,
  })
}

// Usage
const { data: warehouses, isLoading, error } = useWarehouses({ region: 'north' })
```

### useMutation

```jsx
import { useMutation, useQueryClient } from '@tanstack/react-query'

export function useCreateWarehouse() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data) => createWarehouse(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: warehouseKeys.all })
    },
  })
}

// Usage
const { mutate, isPending } = useCreateWarehouse()
mutate({ name: 'North Hub', region: 'north' })
```

### Optimistic Updates

```jsx
export function useUpdateWarehouse() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }) => updateWarehouse(id, data),

    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: warehouseKeys.detail(id) })
      const previous = queryClient.getQueryData(warehouseKeys.detail(id))
      queryClient.setQueryData(warehouseKeys.detail(id), (old) => ({ ...old, ...data }))
      return { previous }
    },

    onError: (_, { id }, context) => {
      queryClient.setQueryData(warehouseKeys.detail(id), context?.previous)
    },

    onSettled: (_, __, { id }) => {
      queryClient.invalidateQueries({ queryKey: warehouseKeys.detail(id) })
    },
  })
}
```

### Server-Side Prefetching (Next.js)

```jsx
import { dehydrate, HydrationBoundary, QueryClient } from '@tanstack/react-query'

export default async function WarehousesPage() {
  const queryClient = new QueryClient()
  await queryClient.prefetchQuery({
    queryKey: warehouseKeys.all,
    queryFn: fetchWarehouses,
  })

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <WarehouseList />
    </HydrationBoundary>
  )
}
```

Pre-fills the client cache from the server — eliminates the initial loading state.

### Rules

- Co-locate query hooks with the domain (`hooks/useWarehouses.js`, `hooks/useShipments.js`).
- Never manually update cache for fresh data — invalidate and refetch.
- Set `staleTime` intentionally. Default `0` refetches on every mount.
- Always handle `isLoading` and `error` in components that use `useQuery`.

---

## Context — Use Sparingly

Appropriate only for values that change rarely and are needed deep in the tree.

```jsx
const ThemeContext = createContext('light')
const AuthContext = createContext(null)
```

**Do not use Context for** lists, entities, or frequently-updated state. When Context value changes, all consumers re-render — Zustand's selector-based access avoids this entirely.
