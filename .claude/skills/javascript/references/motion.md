# Motion (Framer Motion)

Animation patterns using Motion (`motion/react`), the primary UI animation library.

## Import

```tsx
import { motion, AnimatePresence } from 'motion/react'
```

> Package: `motion` (formerly `framer-motion`, rebranded 2025). Import from `'motion/react'`.

## Basic Animation

`motion.*` components accept `initial`, `animate`, `exit`, and `transition` props.

```tsx
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.3, ease: 'easeOut' }}
>
  Content
</motion.div>
```

**Hardware-accelerated properties only** — animate `transform` and `opacity`. Never animate `width`, `height`, `left`, `top`, or background colors — they cause layout thrash and repaints.

```tsx
// ❌ Bad — triggers layout recalculation
<motion.div animate={{ width: 300, left: 100 }} />

// ✅ Good — GPU-accelerated
<motion.div animate={{ scaleX: 1.5, x: 100 }} />
```

## AnimatePresence

Animates components as they mount and unmount. Required for exit animations.

```tsx
<AnimatePresence>
  {isOpen && (
    <motion.div
      key="modal"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      <Modal />
    </motion.div>
  )}
</AnimatePresence>
```

**`mode` prop** controls how multiple children animate:
- `mode="wait"` — exit completes before next enters (default-ish: `"sync"`)
- `mode="popLayout"` — exits the old element from the DOM flow immediately

## Variants System

Define named states and reference them by string. Variants propagate automatically to motion children.

```tsx
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.2,
    },
  },
}

const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0 },
}

export function ProductGrid({ products }) {
  return (
    <motion.ul variants={container} initial="hidden" animate="show">
      {products.map((p) => (
        <motion.li key={p.id} variants={item}>
          <ProductCard {...p} />
        </motion.li>
      ))}
    </motion.ul>
  )
}
```

Variant propagation: when a parent has `animate="show"`, all descendant `motion.*` components with a matching variant state animate automatically — no need to pass `initial`/`animate` on every child.

## Layout Animations

Animate any CSS layout change with the `layout` prop.

```tsx
// Animates position/size changes caused by CSS
<motion.div layout>
  {isExpanded && <DetailPanel />}
</motion.div>
```

**Shared element transitions with `layoutId`**: Morph one element into another across renders.

```tsx
{selectedId === product.id ? (
  <motion.div layoutId={`card-${product.id}`} className="expanded-card">
    <FullProductView product={product} />
  </motion.div>
) : (
  <motion.div layoutId={`card-${product.id}`} className="compact-card">
    <ProductCard product={product} />
  </motion.div>
)}
```

The element morphs from compact → expanded using its `layoutId` as the shared identity.

**Wrap layout animations in `<LayoutGroup>`** when multiple sibling lists affect each other's layout.

## Gestures

```tsx
<motion.button
  whileHover={{ scale: 1.05 }}
  whileTap={{ scale: 0.95 }}
  transition={{ type: 'spring', stiffness: 400, damping: 17 }}
>
  Add to Cart
</motion.button>
```

**Drag**:
```tsx
<motion.div
  drag="x"
  dragConstraints={{ left: -100, right: 100 }}
  dragElastic={0.1}
  onDragEnd={(_, info) => {
    if (info.offset.x > 50) onSwipeRight()
  }}
>
  Swipeable card
</motion.div>
```

**Scroll-triggered** with `whileInView`:
```tsx
<motion.section
  initial={{ opacity: 0, y: 40 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: '-100px' }}
  transition={{ duration: 0.5 }}
>
  Section content
</motion.section>
```

## Motion Values

For smooth programmatic animations without triggering React re-renders.

```tsx
import { useMotionValue, useSpring, useTransform } from 'motion/react'

const x = useMotionValue(0)

// Physics spring
const springX = useSpring(x, { damping: 20, stiffness: 200 })

// Derived value
const opacity = useTransform(x, [-200, 0, 200], [0, 1, 0])

return (
  <motion.div
    style={{ x: springX, opacity }}
    drag="x"
    onDrag={(_, info) => x.set(info.offset.x)}
  />
)
```

Use `useMotionValue` for drag, scroll-linked animations, or cursor-following effects.

## Scroll Animations

```tsx
import { useScroll, useTransform } from 'motion/react'

export function ParallaxHero() {
  const { scrollY } = useScroll()
  const y = useTransform(scrollY, [0, 500], [0, 150])

  return (
    <div style={{ overflow: 'hidden' }}>
      <motion.img src="/hero.jpg" style={{ y }} />
    </div>
  )
}
```

For viewport-relative scroll: `useScroll({ target: ref, offset: ['start end', 'end start'] })`.

## Page Transitions (Next.js)

Wrap page content in a Client Component with `AnimatePresence` at the layout level.

```tsx
// components/PageTransition.tsx
'use client'
import { AnimatePresence, motion } from 'motion/react'
import { usePathname } from 'next/navigation'

export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={pathname}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}
```

## Reduced Motion Accessibility

Always respect `prefers-reduced-motion`. Use the `useReducedMotion` hook.

```tsx
import { useReducedMotion } from 'motion/react'

export function AnimatedCard({ children }) {
  const reduce = useReducedMotion()

  return (
    <motion.div
      initial={{ opacity: 0, y: reduce ? 0 : 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0 : 0.4 }}
    >
      {children}
    </motion.div>
  )
}
```

Or use the `reducedMotion` prop directly on `motion.*` elements:
```tsx
<motion.div
  animate={{ opacity: 1, y: 20 }}
  reducedMotion="user"  // disables y when user prefers reduced motion
/>
```

## Transition Types

```tsx
// Tween (default)
transition={{ duration: 0.3, ease: 'easeInOut' }}

// Spring (natural feel for UI)
transition={{ type: 'spring', stiffness: 300, damping: 25 }}

// Physics spring with mass
transition={{ type: 'spring', mass: 0.5, stiffness: 400, damping: 20 }}

// Stagger children
transition={{ staggerChildren: 0.08, delayChildren: 0.1 }
```

Use spring transitions for interactive elements (hover, tap, drag). Use tween for entrance/exit animations.

## Common Patterns Summary

| Goal | Pattern |
|---|---|
| Entrance animation | `initial` + `animate` on `motion.div` |
| Exit animation | `AnimatePresence` + `exit` prop |
| List stagger | `variants` with `staggerChildren` |
| Shared element morph | `layoutId` |
| CSS layout change | `layout` prop |
| Gesture feedback | `whileHover`, `whileTap` |
| Scroll-linked | `useScroll` + `useTransform` |
| Programmatic | `useMotionValue` + `useSpring` |
| Accessibility | `useReducedMotion` or `reducedMotion="user"` |
