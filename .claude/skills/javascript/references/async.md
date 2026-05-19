# Async Patterns

## async/await

Use `async`/`await` as the default. Always `await` promises — a missing `await` creates a floating promise with silently lost errors.

```js
// Good — clear sequential flow
async function fetchUserPosts(userId) {
  const user = await getUser(userId)
  const posts = await getPosts(user.id)
  return posts
}
```

Use `return await` only inside `try` blocks where you need to catch the error:

```js
// Unnecessary
async function getUser(id) {
  return await fetchUser(id) // just: return fetchUser(id)
}

// Necessary — catch needs the await
async function getUser(id) {
  try {
    return await fetchUser(id)
  } catch (err) {
    return null
  }
}
```

## Error Handling

Wrap `await` in `try`/`catch` only where you handle at that level — let errors propagate to a top-level handler otherwise.

```js
async function loadConfig() {
  try {
    const data = await readFile('config.json', 'utf8')
    return JSON.parse(data)
  } catch (err) {
    if (err.code === 'ENOENT') return DEFAULT_CONFIG
    throw err
  }
}
```

**Never swallow errors.** Every `catch` must handle, rethrow, or report:

```js
// Bad
try { await riskyOperation() } catch (err) {}

// Good
try {
  await riskyOperation()
} catch (err) {
  reportError(err)
  throw err
}
```

Always throw `Error` instances — string throws lose stack traces:

```js
throw new Error('Something went wrong')  // Good
throw 'Something went wrong'             // Bad — no stack trace
```

Attach `.catch()` to fire-and-forget promises:

```js
fetchData().catch(reportError)
```

## Concurrency

Run independent operations in parallel with `Promise.all`:

```js
// Bad — sequential for no reason
const users     = await getUsers()
const shipments = await getShipments()

// Good — parallel
const [users, shipments] = await Promise.all([getUsers(), getShipments()])
```

`Promise.all` rejects on first failure. Use `Promise.allSettled` when all results matter regardless of individual failures:

```js
const results   = await Promise.allSettled([fetchPrimary(), fetchFallback()])
const successes = results.filter((r) => r.status === 'fulfilled').map((r) => r.value)
```

`Promise.race` for timeouts. `Promise.any` for fallbacks (rejects only when ALL reject).

Avoid sequential awaits in loops:

```js
// Bad — sequential
for (const url of urls) {
  const data = await fetch(url)
}

// Good — parallel
const results = await Promise.all(urls.map((url) => fetch(url)))
```

## Cancellation

Use `AbortController` for cancellable fetch calls — essential for React `useEffect` cleanup:

```js
useEffect(() => {
  const controller = new AbortController()

  fetch(url, { signal: controller.signal })
    .then((res) => res.json())
    .then(setData)
    .catch((err) => {
      if (err.name !== 'AbortError') reportError(err)
    })

  return () => controller.abort()
}, [url])
```
