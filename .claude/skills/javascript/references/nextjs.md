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
├── products/
│   ├── page.js        ← /products
│   ├── [id]/
│   │   └── page.js    ← /products/[id]
├── @modal/            ← parallel route slot
│   └── (.)products/[id]/page.js  ← intercepting route
├── api/
│   └── webhook/
│       └── route.js   ← API route handler
└── actions/
    └── products.js    ← Server Actions
```

**`error.js` must be a Client Component** — it uses React Error Boundary API.

## React Server Components

All components are Server Components by default. They can be `async`.

```jsx
// app/products/page.js — Server Component
export default async function ProductsPage() {
  const products = await db.product.findMany()
  return (
    <ul>
      {products.map((p) => (
        <ProductRow key={p.id} {...p} />
      ))}
    </ul>
  )
}
```

**Push `'use client'` to leaf components only.** When a parent is marked `'use client'`, its entire subtree becomes client-side.

```jsx
// components/AddToCartButton.js — leaf interactive component
'use client'
import { useState } from 'react'

export function AddToCartButton({ productId }) {
  const [loading, setLoading] = useState(false)
  return <button onClick={...}>Add to cart</button>
}
```

## Data Fetching in Server Components

Fetch directly in async Server Components.

```jsx
// Cached, revalidated every hour
const res = await fetch('https://api.example.com/products', {
  next: { revalidate: 3600, tags: ['products'] },
})

// Always fresh
const res = await fetch('https://api.example.com/live', {
  cache: 'no-store',
})
```

**Deduplicate with `cache()`**: Same function called in multiple components within one render = 1 network call.

```jsx
import { cache } from 'react'

export const getProduct = cache(async (id) => {
  return db.product.findUnique({ where: { id } })
})
```

## Server Actions

Mutations that run on the server. Define with `'use server'`.

```jsx
// app/actions/products.js
'use server'

import { revalidateTag } from 'next/cache'
import { redirect } from 'next/navigation'

export async function createProduct(formData) {
  const name = formData.get('name')
  const price = Number(formData.get('price'))

  await db.product.create({ data: { name, price } })
  revalidateTag('products')
  redirect('/products')
}
```

**Use in forms** (no JS required):
```jsx
<form action={createProduct}>
  <input name="name" />
  <input name="price" type="number" />
  <button type="submit">Create</button>
</form>
```

**React 19 hooks** for richer client-side integration:
```jsx
'use client'
import { useActionState } from 'react'

export function CreateProductForm() {
  const [state, action, isPending] = useActionState(createProduct, null)

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
await fetch('/api/products', { next: { tags: ['products'] } })

// Invalidate all pages that fetched with this tag
revalidateTag('products')
```

**Path-based invalidation** (single route):
```jsx
revalidatePath('/products')
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
      <Suspense fallback={<SalesSkeleton />}>
        <SalesChart />
      </Suspense>
      <Suspense fallback={<BillsSkeleton />}>
        <RecentBills />
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
  title: 'Products | CloudSale',
  description: 'Manage your product catalog',
}

// Dynamic
export async function generateMetadata({ params }) {
  const product = await getProduct(params.id)
  return {
    title: `${product.name} | CloudSale`,
  }
}
```

## Image, Font, Script Optimization

```jsx
// Image — always specify width/height to prevent layout shift
import Image from 'next/image'
<Image src={product.imageUrl} alt={product.name} width={400} height={300} />

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
// app/api/products/route.js
export async function GET(request) {
  const products = await db.product.findMany()
  return Response.json(products)
}

export async function POST(request) {
  const body = await request.json()
  const product = await db.product.create({ data: body })
  return Response.json(product, { status: 201 })
}
```

## Parallel and Intercepting Routes

**Parallel routes** (`@slot`): Render multiple pages simultaneously in the same layout.

**Intercepting routes** (`(.)`, `(..)`): Show different UI at the same URL without full navigation.

Use together for modals with deep-linkable URLs — e.g. clicking a product opens a modal at `/products/[id]`, but navigating directly renders the full page.
