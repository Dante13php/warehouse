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
// stores/productStore.js
import { create } from 'zustand'
import { devtools } from 'zustand/middleware'

export const useProductStore = create(
  devtools(
    (set) => ({
      selectedIds: [],
      selectProduct: (id) =>
        set((s) => ({ selectedIds: [...s.selectedIds, id] })),
      deselectProduct: (id) =>
        set((s) => ({ selectedIds: s.selectedIds.filter((x) => x !== id) })),
      clearSelection: () => set({ selectedIds: [] }),
    }),
    { name: 'ProductStore' }
  )
)
```

### Selective Access

```jsx
// ✅ Re-renders only when selectedIds changes
const selectedIds = useProductStore((s) => s.selectedIds)

// ❌ Re-renders on any store change
const store = useProductStore()
```

Always use a selector function. Never destructure the whole store.

### Slices Pattern (Large Stores)

```js
// stores/slices/billSlice.js
export const createBillSlice = (set) => ({
  activeBillId: null,
  setActiveBill: (id) => set({ activeBillId: id }),
})

// stores/appStore.js
import { create } from 'zustand'
import { createBillSlice } from './slices/billSlice'
import { createUserSlice } from './slices/userSlice'

export const useAppStore = create((...args) => ({
  ...createBillSlice(...args),
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
    { name: 'cloudsale-settings' }
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
export const productKeys = {
  all: ['products'],
  list: (filters) => [...productKeys.all, filters],
  detail: (id) => ['product', id],
}
```

### useQuery

```jsx
import { useQuery } from '@tanstack/react-query'

export function useProducts(filters) {
  return useQuery({
    queryKey: productKeys.list(filters),
    queryFn: () => fetchProducts(filters),
    staleTime: 5 * 60 * 1000,
  })
}

// Usage
const { data: products, isLoading, error } = useProducts({ status: 'active' })
```

### useMutation

```jsx
import { useMutation, useQueryClient } from '@tanstack/react-query'

export function useCreateProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data) => createProduct(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: productKeys.all })
    },
  })
}

// Usage
const { mutate, isPending } = useCreateProduct()
mutate({ name: 'Espresso', price: 2.5 })
```

### Optimistic Updates

```jsx
export function useUpdateProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }) => updateProduct(id, data),

    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: productKeys.detail(id) })
      const previous = queryClient.getQueryData(productKeys.detail(id))
      queryClient.setQueryData(productKeys.detail(id), (old) => ({ ...old, ...data }))
      return { previous }
    },

    onError: (_, { id }, context) => {
      queryClient.setQueryData(productKeys.detail(id), context?.previous)
    },

    onSettled: (_, __, { id }) => {
      queryClient.invalidateQueries({ queryKey: productKeys.detail(id) })
    },
  })
}
```

### Server-Side Prefetching (Next.js)

```jsx
import { dehydrate, HydrationBoundary, QueryClient } from '@tanstack/react-query'

export default async function ProductsPage() {
  const queryClient = new QueryClient()
  await queryClient.prefetchQuery({
    queryKey: productKeys.all,
    queryFn: fetchProducts,
  })

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <ProductList />
    </HydrationBoundary>
  )
}
```

Pre-fills the client cache from the server — eliminates the initial loading state.

### Rules

- Co-locate query hooks with the domain (`hooks/useProducts.js`, `hooks/useBills.js`).
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
