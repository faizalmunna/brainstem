---
name: nextjs-server-client-boundary
description: Diagnose Next.js App Router errors at the Server/Client Component boundary -- serialization errors, "use client" missing, accidental client bundle bloat.
triggers: ["use client error", "cannot pass function to client component", "server component error", "functions cannot be passed directly to client components", "hydration error nextjs app router"]
permissions: ["READ"]
---

## Symptom
One of: a build/runtime error like "Functions cannot be passed directly
to Client Components" or "Only plain objects can be passed to Client
Components"; a component that needs `useState`/`useEffect`/browser APIs
failing because it's still a Server Component; or a Client Component
accidentally pulling a large server-only dependency into the client
JavaScript bundle.

## Likely causes
1. **Passing a function (including a closure over server-only state) as a
   prop from a Server Component into a Client Component** -- functions
   aren't serializable across the RSC boundary except as Server Actions.
2. **Missing `"use client"` directive** on a component that uses
   `useState`, `useEffect`, `useContext`, event handlers, or any
   browser-only API -- it's being treated as a Server Component and
   either errors or silently can't do what it's trying to do.
3. **A Client Component importing a server-only or heavy module**
   (a database client, a Node-only package) at the top level, pulling it
   into the client bundle even if it's never actually called client-side.
4. **Passing a non-plain object** (a class instance, a Map/Set, a Date in
   some configurations) from Server to Client Component -- only
   JSON-serializable-ish values cross the boundary.
5. **A third-party component library not marked `"use client"` internally**
   being used inside what you assumed was a Server Component tree,
   causing an unexpected boundary in the middle of your own component.

## Diagnose
- Read the exact error: Next.js/React usually names the specific prop or
  value that failed to serialize.
- Trace which component the offending value originates in, and confirm
  whether that component (and everything importing it) has `"use client"`
  at the top, or whether it should actually stay server-only and pass
  data (not a function) down instead.
- For unexpected bundle-size increases, use `next build` with the bundle
  analyzer to see which Client Component pulled in a server-only
  dependency, then check its imports.

## Fix
- Don't pass functions across the boundary for behavior that must run on
  the server; use a Server Action (`"use server"` function) passed as a
  prop instead, or move the interactive logic entirely into a Client
  Component that calls a fetch/Server Action itself.
- Add `"use client"` at the top of any component (and, transitively, any
  module it imports that also needs client behavior) that uses hooks or
  browser APIs -- keep the directive as close to the leaf as possible
  rather than marking a large shared tree client-side unnecessarily.
- Pass only plain, serializable data (strings, numbers, plain objects/
  arrays, and Server Actions) as props from Server to Client Components;
  convert dates/Maps/etc. to plain representations before passing them
  down.
- Move server-only imports out of files that also get imported by Client
  Components; split into a server-only module and a client-safe module
  if a file currently mixes both concerns.

## Pitfalls
- Adding `"use client"` to a large shared layout/page component "to make
  the error go away" turns the whole subtree into client-rendered code,
  losing the server-rendering/bundle-size benefits for everything under
  it -- push the directive down to the smallest actually-interactive leaf.
- Serializing a function by wrapping it (e.g. `{ fn: fn.toString() }`) to
  work around the passing-functions error reintroduces the same problem
  in a harder-to-debug form and is a security smell if the string is ever
  evaluated.

## Verify
Run a production build (`next build`) rather than relying on dev mode
alone -- some serialization and bundling issues only surface there -- and
confirm the specific route/component compiles and the client bundle for
that route didn't grow from a server-only import leaking in.
