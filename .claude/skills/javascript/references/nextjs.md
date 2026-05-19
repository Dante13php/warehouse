# Next.js App Router

Patterns for Next.js 14/15 with App Router and React Server Components.

## Folder Conventions

```
app/
├── layout.js          ← root layout, wraps all pages
├── page.js            ← home route (/)
├── loading.js         ← Suspense boundary for the segment
├── error.js           ← Error Boundary for the segment ('use client')
├── not-found.js       ← custom 404 for the segment
├── warehouses/
│   ├── page.js        ← /warehouses
│   ├── [id]/
│   │   └── page.js    ← /warehouses/[id]
├── @modal/            ← parallel route slot
│   └── (.)warehouses/[id]/page.js  ← intercepting route
├── api/
│   └── webhook/
│       └── route.js   ← API route handler
└── actions/
    └── warehouses.js  ← Server Actions
```

**`error.js` must be a Client Component** — it uses React Error Boundary API.

## React Server Components

All components are Server Components by default. They can be `async`.

```jsx
// app/warehouses/page.js — Server Component
export default async function WarehousesPage() {
  const warehouses = await db.warehouse.findMany()
  return (
    <ul>
      {warehouses.map((w) => (
        <WarehouseRow key={w.id} {...w} />
      ))}
    </ul>
  )
}
```

**Push `'use client'` to leaf components only.** When a parent is marked `'use client'`, its entire subtree becomes client-side.

```jsx
// components/UpdateStockButton.js — leaf interactive component
'use client'
import { useState } from 'react'

export function UpdateStockButton({ warehouseId }) {
  const [loading, setLoading] = useState(false)
  return <button onClick={...}>Update stock</button>
}
```

## Data Fetching in Server Components

Fetch directly in async Server Components.

```jsx
// Cached, revalidated every hour
const res = await fetch('https://api.example.com/warehouses', {
  next: { revalidate: 3600, tags: ['warehouses'] },
})

// Always fresh
const res = await fetch('https://api.example.com/live', {
  cache: 'no-store',
})
```

**Deduplicate with `cache()`**: Same function called in multiple components within one render = 1 network call.

```jsx
import { cache } from 'react'

export const getWarehouse = cache(async (id) => {
  return db.warehouse.findUnique({ where: { id } })
})
```

## Server Actions

Mutations that run on the server. Define with `'use server'`.

```jsx
// app/actions/warehouses.js
'use server'

import { revalidateTag } from 'next/cache'
import { redirect } from 'next/navigation'

export async function createWarehouse(formData) {
  const name = formData.get('name')
  const region = formData.get('region')

  await db.warehouse.create({ data: { name, region } })
  revalidateTag('warehouses')
  redirect('/warehouses')
}
```

**Use in forms** (no JS required):
```jsx
<form action={createWarehouse}>
  <input name="name" />
  <input name="region" />
  <button type="submit">Create</button>
</form>
```

**React 19 hooks** for richer client-side integration:
```jsx
'use client'
import { useActionState } from 'react'

export function CreateWarehouseForm() {
  const [state, action, isPending] = useActionState(createWarehouse, null)

  return (
    <form action={action}>
      <input name="name" />
      <button disabled={isPending}>{isPending ? 'Creating…' : 'Create'}</button>
      {state?.error && <p>{state.error}</p>}
    </form>
  )
}
```

## Caching Strategy

| Layer | What | Invalidate |
|---|---|---|
| Request Memoization | Deduplicates `fetch` calls within one render | Automatic |
| Data Cache | Caches `fetch` responses on the server | `revalidateTag()`, `revalidatePath()` |
| Full Route Cache | Pre-rendered HTML for static routes | `revalidatePath()`, redeploy |
| Router Cache | Client-side in-memory RSC payload | `router.refresh()`, Server Action |

**Tag-based invalidation** (preferred for shared data):
```jsx
// Fetch with tag
await fetch('/api/warehouses', { next: { tags: ['warehouses'] } })

// Invalidate all pages that fetched with this tag
revalidateTag('warehouses')
```

**Path-based invalidation** (single route):
```jsx
revalidatePath('/warehouses')
```

## Static vs Dynamic Rendering

**Static (default)**: Pre-rendered at build time. Fast, CDN-cacheable.

**Dynamic**: Rendered per request. Triggered automatically by:
- Calling `cookies()` or `headers()`
- Using `searchParams` in `page.js`
- Using `fetch` with `{ cache: 'no-store' }`

Force dynamic:
```jsx
export const dynamic = 'force-dynamic'
```

**Partial Pre-Rendering (PPR, Next.js 15)**: Static shell + streamed dynamic holes.
```jsx
export default function Page() {
  return (
    <>
      <StaticHeader />
      <Suspense fallback={<Skeleton />}>
        <DynamicFeed />
      </Suspense>
    </>
  )
}
```

## Streaming with Suspense

Wrap slow async Server Components in `<Suspense>` to stream them after the static shell.

```jsx
export default function DashboardPage() {
  return (
    <main>
      <h1>Dashboard</h1>
      <Suspense fallback={<InventorySkeleton />}>
        <InventoryChart />
      </Suspense>
      <Suspense fallback={<MovementsSkeleton />}>
        <RecentMovements />
      </Suspense>
    </main>
  )
}
```

`loading.js` in a folder automatically wraps the page in `<Suspense>`.

## Metadata API

```jsx
// Static
export const metadata = {
  title: 'Warehouses | Warehouse',
  description: 'Manage your warehouses',
}

// Dynamic
export async function generateMetadata({ params }) {
  const warehouse = await getWarehouse(params.id)
  return {
    title: `${warehouse.name} | Warehouse`,
  }
}
```

## Image, Font, Script Optimization

```jsx
// Image — always specify width/height to prevent layout shift
import Image from 'next/image'
<Image src={warehouse.imageUrl} alt={warehouse.name} width={400} height={300} />

// Font — self-hosted, zero layout shift
import { Inter } from 'next/font/google'
const inter = Inter({ subsets: ['latin'] })

// Script — lazy load third-party scripts
import Script from 'next/script'
<Script src="https://analytics.example.com/script.js" strategy="lazyOnload" />
```

## Route Handlers

Use for public APIs, webhooks, streaming — not for internal mutations (use Server Actions).

```jsx
// app/api/warehouses/route.js
export async function GET(request) {
  const warehouses = await db.warehouse.findMany()
  return Response.json(warehouses)
}

export async function POST(request) {
  const body = await request.json()
  const warehouse = await db.warehouse.create({ data: body })
  return Response.json(warehouse, { status: 201 })
}
```

## Parallel and Intercepting Routes

**Parallel routes** (`@slot`): Render multiple pages simultaneously in the same layout.

**Intercepting routes** (`(.)`, `(..)`): Show different UI at the same URL without full navigation.

Use together for modals with deep-linkable URLs — e.g. clicking a warehouse opens a modal at `/warehouses/[id]`, but navigating directly renders the full page.
