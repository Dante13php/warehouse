# Objects and Arrays

## Immutable Updates

Never mutate objects or arrays — return new ones. This is critical for React state correctness.

```js
const added   = [...items, newItem]
const removed = items.filter((_, i) => i !== index)
const updated = items.map((item) =>
  item.id === target.id ? { ...item, ...changes } : item
)

// Object
const next = { ...user, role: 'admin' }

// Omit a key
const { password, ...safeUser } = user
```

## Spread and Merge

```js
const copy   = { ...original }
const merged = { ...defaults, ...overrides }
const combined = [...arr1, ...arr2]
```

Prefer spread over `Object.assign()`.

## Destructuring

```js
// Object
const { name, email } = user
const { role = 'user', active = true } = options
const { name: userName } = user  // rename

// Parameter destructuring
function formatUser({ name, email, role = 'user' }) {
  return `${name} <${email}> (${role})`
}

// Array
const [first, ...rest] = items
```

Return objects for multiple values — callers don't depend on order:

```js
// Bad
function getRange() { return [min, max] }

// Good
function getRange() { return { min, max } }
```

## Iteration Decision Table

| Goal | Use |
|---|---|
| Transform → new array | `.map()` |
| Filter items | `.filter()` |
| Accumulate to single value | `.reduce()` |
| Find first match | `.find()` / `.findIndex()` |
| Check condition | `.some()` / `.every()` |
| Side effects on each item | `for...of` |
| Async sequential processing | `for...of` with `await` |
| Object keys/values | `Object.entries()` + `for...of` |

Don't use `for...in` on arrays — it iterates string keys including inherited properties.

## Object Iteration

```js
for (const [key, value] of Object.entries(obj)) { ... }
for (const key of Object.keys(obj)) { ... }
for (const value of Object.values(obj)) { ... }
```

## Map and Set

Use `Map` when keys are not strings or are user-provided (avoids prototype pollution). Use `Set` for deduplication.

```js
const cache = new Map()
cache.set(objectKey, value)

const deduped = [...new Set(items)]
```

## Functional Array Methods

Always return in `map`, `filter`, `reduce` callbacks. Prefer declarative over imperative loops for data transformation.

```js
// Bad
const active = []
for (let i = 0; i < users.length; i++) {
  if (users[i].active) active.push(users[i])
}

// Good
const active = users.filter((u) => u.active)
```
