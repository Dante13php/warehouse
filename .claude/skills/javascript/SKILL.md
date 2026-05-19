---
name: frontend
description: >-
  React + Next.js frontend implementation conventions for CloudSale. Invoke whenever a task
  involves any interaction with JavaScript code — writing, reviewing, refactoring, debugging,
  or shared frontend structure. Covers React component patterns, Next.js App Router,
  Motion animations, and state management.
---

# Frontend

**Clarity is the highest virtue. If your code requires a comment to explain its control flow, rewrite it.**

The stack is **React 18/19 + Next.js App Router + Motion (framer-motion) + Zustand + TanStack Query**.

## References

- **React component patterns, hooks, performance** → [`${CLAUDE_SKILL_DIR}/references/react-components.md`]
- **Next.js App Router, RSC, data fetching, caching** → [`${CLAUDE_SKILL_DIR}/references/nextjs.md`]
- **Motion animations (framer-motion)** → [`${CLAUDE_SKILL_DIR}/references/motion.md`]
- **State management (Zustand + TanStack Query)** → [`${CLAUDE_SKILL_DIR}/references/state.md`]
- **Functions, closures, composition** → [`${CLAUDE_SKILL_DIR}/references/functions.md`]
- **Async patterns, error handling, concurrency** → [`${CLAUDE_SKILL_DIR}/references/async.md`]
- **Objects, arrays, iteration** → [`${CLAUDE_SKILL_DIR}/references/objects-and-arrays.md`]
- **ES modules, imports** → [`${CLAUDE_SKILL_DIR}/references/modules.md`]

## Variables and Declarations

- `const` by default. `let` only when reassignment is required. Never `var`.
- One declaration per line. Group `const` first, then `let`.

## Naming

| Entity | Style | Examples |
|---|---|---|
| Variables, functions | camelCase | `userName`, `fetchData` |
| Components, classes | PascalCase | `ProductCard`, `UserService` |
| True compile-time constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `API_BASE_URL` |
| Booleans | `is`/`has`/`can`/`should` prefix | `isLoading`, `hasAccess` |
| Component files | PascalCase | `ProductCard.jsx` |
| Utility/hook files | camelCase | `useProducts.js`, `formatPrice.js` |
| Route segments | kebab-case | `product-catalog/` |

## Equality and Safety

- Always `===` and `!==`. Only `==` for `value == null`.
- `??` over `||` for defaults — `||` treats `0`, `""`, `false` as falsy.
- `?.` for optional chaining. Missing required data should throw, not silently return `undefined`.
- Logical assignment: `opts.timeout ??= 5000` (assign if nullish), `opts.name ||= 'default'` (assign if falsy), `opts.handler &&= wrap(opts.handler)` (assign if truthy).

## Functions

- Arrow functions for callbacks and anonymous functions.
- Destructured options objects for 3+ parameters.
- Early return. Guard clauses first, happy path flat.
- One function, one job.
- Pure functions by default. Isolate side effects explicitly.

## Async

- `async`/`await` over `.then()` chains.
- `Promise.all` for independent parallel work.
- Always `await` promises.
- Never swallow errors.

## Modules

- Named exports over default exports. Exception: Next.js pages/layouts require default exports.
- Imports at the top, grouped: external packages → internal (`@/`) → relative (`./`).
- No barrel files in feature folders.
- Dynamic imports (`next/dynamic`) for code splitting.

## Component File Structure

```jsx
// 1. Imports
import { useState } from 'react'
import { motion } from 'motion/react'
import { useProductStore } from '@/stores/productStore'

// 2. Component
export function ProductCard({ id, name, price }) {
  // hooks first
  const [isExpanded, setIsExpanded] = useState(false)

  // derived values
  const formattedPrice = formatPrice(price)

  // handlers
  const handleToggle = () => setIsExpanded((prev) => !prev)

  // render
  return (
    <motion.div layout onClick={handleToggle}>
      <h3>{name}</h3>
      <span>{formattedPrice}</span>
    </motion.div>
  )
}
```

## UI Planning and Implementation

- Default to Server Components. Add `'use client'` only at the leaf component that needs interactivity.
- Use Motion (`motion/react`) for all animations.
- Use Zustand for client-side UI state. Use TanStack Query for server-derived data.
- Prefer `next/image` over `<img>`. Prefer `next/font` over `@import` for fonts.
- Split heavy components with `next/dynamic`. Virtualize lists over 50–100 items.
- Keep Server Actions in `app/actions/` or co-located `actions.js` files.
- Wrap data-fetching boundaries with `<Suspense>` for streaming.
- Place Error Boundaries at feature level, not app root.

## Code Review

When **reviewing** code, cite the specific violation and show the fix inline. Don't lecture.

```
Bad:  "According to best practices you should avoid useEffect for data fetching."
Good: "useEffect fetch → move to TanStack Query useQuery; handles caching, dedup, and loading state."
```

## Code Navigation — LSP Required

A `typescript-language-server` LSP is configured for JS/JSX files. **Use LSP tools for navigation instead of Grep/Glob.** Use `goToDefinition`, `findReferences`, `hover`, `workspaceSymbol`, `goToImplementation`, `incomingCalls`, `outgoingCalls`.

Grep/Glob remain appropriate for: string literals, log messages, TODO markers, CSS classes, file name patterns.
