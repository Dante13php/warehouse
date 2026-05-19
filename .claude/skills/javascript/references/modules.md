# Modules

ES module patterns for JavaScript + Next.js projects.

## Exports

### Named Exports by Default

Use named exports. They enforce consistent naming and enable tree-shaking.

```js
export function createProduct(data) { ... }
export const MAX_RETRIES = 3
```

**Exception**: Next.js requires default exports for `page.js`, `layout.js`, `loading.js`, `error.js`, and `route.js` files.

```jsx
// app/products/page.js — Next.js requires default export
export default function ProductsPage() { ... }
```

### Don't Export Mutable Bindings

```js
// Bad
export let count = 0

// Good
let count = 0
export function getCount() { return count }
```

## Imports

### Path Aliases — Use `@/`

Use the `@/` alias (configured in `jsconfig.json`) for all project imports. No `../../` chains.

```js
// Bad
import { ProductCard } from '../../../components/ProductCard'

// Good
import { ProductCard } from '@/components/ProductCard'
import { useProducts } from '@/hooks/useProducts'
```

Relative imports (`./`) are acceptable only within the same directory.

### Import Ordering

Group imports with a blank line between each group:

1. External packages (`react`, `next/*`, `motion/react`)
2. Internal aliases (`@/components`, `@/hooks`)
3. Relative (`./utils`)

```js
import { useState } from 'react'
import { motion } from 'motion/react'

import { useProductStore } from '@/stores/productStore'

import { formatPrice } from './utils'
```

### Merge Imports from the Same Module

```js
// Bad
import { useState } from 'react'
import { useEffect } from 'react'

// Good
import { useState, useEffect } from 'react'
```

## Barrel Files

Acceptable **at the component library level** to define a public API:

```js
// components/ui/index.js
export { Button } from './Button'
export { Input } from './Input'
export { Modal } from './Modal'
```

**Do not create barrel files** in feature folders — they create import ambiguity and hurt tree-shaking.

```js
// Bad — internal barrel
// features/products/index.js
export * from './ProductList'
export * from './ProductCard'

// Good — import directly
import { ProductList } from '@/features/products/ProductList'
```

## Dynamic Imports

Use `next/dynamic` for heavy components not needed on initial render.

```js
import dynamic from 'next/dynamic'

const HeavyChart = dynamic(() => import('@/components/HeavyChart'), {
  loading: () => <ChartSkeleton />,
  ssr: false,
})
```

## No Circular Dependencies

If A imports B and B imports A, one sees an incomplete module at initialization.

Fix: extract shared code to `@/lib/shared`, or pass dependencies as arguments.

## Side-Effect Imports

Rare. Always document why.

```js
// Registers global polyfill — required before any crypto usage
import '@/lib/polyfills'
```
