---
name: route-model-binding-key-mismatch
description: A route returns a 404 or resolves the wrong record because the route parameter value does not match the model's actual binding key column.
triggers: ["laravel route model binding 404", "route model binding wrong record", "implicit binding not working laravel", "route parameter not matching model"]
permissions: ["READ"]
---

## Symptom
A route like `Route::get('/posts/{post:slug}', ...)` (or a plain
`{post}` implicit binding) returns a 404 for a URL that clearly
corresponds to a real record, or worse, silently resolves to the *wrong*
record -- and the same controller works fine when tested with a
different identifier format, making the bug look request-specific rather
than structural.

## Likely causes
1. **The route parameter name doesn't match the controller method's
   argument name.** Implicit binding matches by name -- `{post}` in the
   route must correspond to a `$post` parameter in the controller method;
   a mismatch (`{post}` in the route, `$article` in the method) causes
   Laravel to fail to bind and either 404s or falls back to passing the
   raw value.
2. **The model overrides `getRouteKeyName()` (or the route explicitly
   specifies `{post:slug}`), but the value in the URL was generated
   using the primary key (id) instead of the intended key (slug)** --
   e.g. a link/redirect elsewhere in the app was built with
   `route('posts.show', $post->id)` after the binding key was changed to
   `slug`, so old-style numeric URLs now 404 against a column that
   doesn't contain numbers.
3. **A global scope or `SoftDeletes` on the model excludes the record from
   the default query implicit binding uses**, so a soft-deleted or
   scoped-out record 404s even though the row exists in the table --
   this looks identical to "the record doesn't exist" from the outside.
4. **Middleware order puts a middleware that needs the resolved model
   (e.g. an authorization middleware checking `$post->user_id`) before
   the model binding itself has run**, or a route group's binding
   `scopeBindings()` behavior wasn't applied where nested resource routes
   are expected to scope the child to the parent (`{user}/{post}`
   resolving `{post}` globally instead of scoped to `{user}`).
5. **Two routes with overlapping URL shapes are registered in the wrong
   order**, so a more specific route (`/posts/featured`) is shadowed by a
   more generic one registered earlier (`/posts/{post}`), and `"featured"`
   gets passed into the binding as if it were a slug/id, which then 404s
   or throws a type error.

## Diagnose
- Run `php artisan route:list --path=posts` (adjust path) to see the
  exact registered route, its parameter name, and the middleware stack
  and order applied to it.
- Check the model for `getRouteKeyName()` and compare it against the
  actual value used in the failing URL -- confirm which column the
  binding is querying against versus which column the URL's value
  actually belongs to.
- Temporarily dump the raw route parameter before binding resolves (or
  check the exception page's SQL query if using `APP_DEBUG=true`) to see
  the exact `WHERE` clause implicit binding generated, and run that query
  directly against the database to see if it should have matched.
- Check the model for global scopes (`static::addGlobalScope(...)`) or
  `SoftDeletes`, and re-run the same lookup with
  `Model::withoutGlobalScopes()->where(...)` to see if the record exists
  but is being filtered out.
- For nested resource routes, check whether `Route::resource(...)
  ->scoped([...])` or manual `scopeBindings()` is applied, and whether
  the child model actually has a relationship method matching the parent
  parameter name that implicit scoped binding relies on.

## Fix
- Keep route parameter names and controller argument names identical and
  intentional -- when renaming one, grep for every route definition and
  every controller method signature that references it, since implicit
  binding silently degrades instead of erroring loudly on a mismatch.
- When changing `getRouteKeyName()` on a model that already has
  production links (bookmarks, emails, external references) pointing at
  the old key format, keep a fallback resolver (override
  `resolveRouteBinding()` to try the new key first, then fall back to
  primary key lookup) for a transition period rather than breaking every
  existing link immediately.
- For soft-deleted or globally-scoped models where the route legitimately
  needs to reach a scoped-out record (e.g. an admin "restore" screen),
  override `resolveRouteBinding()` on that specific route/controller to
  query `withoutGlobalScopes()` or `withTrashed()` explicitly, rather than
  removing the global scope from the model entirely.
- Register more specific static routes before parameterized ones of the
  same shape (`/posts/featured` before `/posts/{post}`), and use
  `whereNumber()`/`where()` route constraints on the parameter to prevent
  a generic route from swallowing URLs it was never meant to match.
- For nested resources, apply `scopeBindings()` (or the resource's
  `->scoped()`) explicitly and ensure the child model has a relationship
  method whose name matches the parent's route parameter, so Laravel can
  automatically scope the child query to the parent instead of doing a
  global lookup.

## Pitfalls
- Silencing the 404 by wrapping the controller in a try/catch and
  returning a generic error hides the real problem (wrong key, wrong
  scope) and turns a diagnosable routing bug into a vague "something went
  wrong" that's much harder to debug later.
- Overriding `resolveRouteBinding()` to fall back through multiple
  strategies indefinitely (try slug, then id, then email, ...) instead of
  migrating old links, accumulates permanent complexity and ambiguity
  about which identifier a URL is actually supposed to use -- treat a
  fallback as a temporary migration aid with a removal plan, not a
  permanent feature.
- Removing a global scope from the model entirely just to make one route
  work exposes soft-deleted/restricted records to every other query in
  the app that relied on that scope being applied by default -- scope the
  fix to the specific route/binding, not the model globally.

## Verify
Hit the exact failing URL after the fix and confirm it returns the
expected record (check the resolved model's primary key or a
distinguishing field in the response, not just a 200 status). Then run
`php artisan route:list --path=<prefix>` and manually confirm route
registration order and parameter names match the controller for every
route sharing that URL prefix, including the previously-shadowed generic
route.
