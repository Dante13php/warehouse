# JavaScript Functions

## Arrow Functions and `this`

Arrow functions capture `this` from the enclosing lexical scope — they do NOT have their own `this`.

```js
// Good — arrow preserves `this` from class method
class Timer {
  start() {
    this.id = setInterval(() => this.tick(), 1000)
  }
}

// Bad — regular function loses `this`
class Timer {
  start() {
    this.id = setInterval(function () {
      this.tick() // TypeError
    }, 1000)
  }
}
```

Never use arrow functions as object methods:

```js
// Bad — arrow captures module-level this, not the object
const obj = {
  name: 'test',
  greet: () => `Hello, ${this.name}`, // undefined
}

// Good
const obj = {
  name: 'test',
  greet() { return `Hello, ${this.name}` },
}
```

## Destructured Options

For functions with 3+ parameters, use a destructured options object:

```js
// Bad — positional args are hard to remember
function createUser(name, email, role, active) { ... }

// Good — self-documenting, order-independent
function createUser({ name, email, role = 'user', active = true }) { ... }
createUser({ name: 'Alice', email: 'a@b.com', role: 'admin' })
```

## Pure Functions

Prefer pure functions. Isolate side effects — don't hide them inside data transformations.

```js
// Impure — mutates input
const addItem = (cart, item) => {
  cart.push(item)
  return cart
}

// Pure — returns new array
const addItem = (cart, item) => [...cart, item]
```

## Early Return

Guard clauses first, happy path flat:

```js
// Bad — deep nesting
function getUser(id) {
  if (id) {
    const user = db.find(id)
    if (user) {
      if (user.active) return user
    }
  }
  return null
}

// Good — flat
function getUser(id) {
  if (!id) return null
  const user = db.find(id)
  if (!user) return null
  if (!user.active) return null
  return user
}
```

## Composition Over Branching

One function, one job. If the name contains "and", split it.

```js
// Bad
function validateAndSave(user) { ... }

// Good
function validate(user) { ... }
function save(user) { ... }

// Compose
const process = pipe(normalize, validate, transform, persist)
```
