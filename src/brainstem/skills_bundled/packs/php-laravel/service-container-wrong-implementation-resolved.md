---
name: service-container-wrong-implementation-resolved
description: Type-hinting an interface in a constructor resolves an unexpected or outdated implementation instead of the one registered for the current context.
triggers: ["laravel container resolving wrong class", "interface binding not working laravel", "dependency injection wrong implementation laravel", "service provider binding order bug"]
permissions: ["READ"]
---

## Symptom
A class type-hints an interface (`PaymentGateway $gateway`) in its
constructor expecting the container to inject a specific implementation
(e.g. `StripeGateway`), but at runtime it receives a different
implementation than expected -- either a default/fallback class, a
previous version left over from a refactor, or (in tests) a completely
different implementation than what's bound in the app's normal service
providers.

## Likely causes
1. **No explicit binding exists for the interface at all**, and Laravel's
   container is falling back to auto-resolving a concrete class with a
   coincidentally matching name, or throwing/resolving `null` in a way
   that gets silently handled -- this happens when a new implementation
   class is added but the corresponding `$this->app->bind(Interface::class,
   Implementation::class)` call in a service provider is never added or
   is added to the wrong provider.
2. **Two service providers bind the same interface to different
   implementations, and provider load order determines which one wins**
   -- the later-registered binding overwrites the earlier one, so an
   ordering change in `config/app.php`'s `providers` array (or the order
   packages are auto-discovered) silently flips which implementation gets
   resolved, with no error anywhere.
3. **A conditional binding based on environment/config is evaluated at
   the wrong time** -- e.g. `if (config('services.payment.driver') ===
   'stripe')` inside a provider's `register()` method, but `register()`
   runs before all config files are guaranteed loaded/merged in a
   specific edge case (config loaded from a package, or set later by
   another provider), so the condition reads a default/stale value.
4. **A test or a testing service provider overrides the binding globally**
   via `$this->app->bind()` in a base test case's `setUp()`, and that
   override leaks into a test that expected the real implementation
   because the binding was registered as a singleton and never reset
   between tests, or because a fake was bound in `TestCase::setUp()` too
   broadly (for all tests, not just the ones that need it).
5. **Contextual binding was intended but a plain binding was used
   instead** -- the app has two consumers of the same interface that
   should get different implementations (`$this->app->when(ClassA::class)
   ->needs(Interface::class)->give(ImplA::class)`), but a single
   non-contextual `bind()` call was used, so every consumer gets whichever
   implementation was bound last, not the one meant for it.

## Diagnose
- Run `php artisan tinker` and call `app(Interface::class)::class` (or
  `get_class(app(Interface::class))`) to see exactly what the container
  resolves right now, independent of any specific request/test.
- Grep the whole codebase for every `->bind(`, `->singleton(`, and
  `->when(...)->needs(...)->give(` call referencing that interface --
  duplicate bindings across multiple service providers are the most
  common root cause and are easy to miss when they're in different files.
- Check `config/app.php`'s `providers` array (or `bootstrap/providers.php`
  on Laravel 11+) and package auto-discovery order (`composer show
  --tree`, or `artisan package:discover` output) for which provider
  registers last -- in Laravel, the last registered binding for a given
  abstract wins.
- If a conditional binding is involved, `dd(config('the.driver.key'))`
  directly inside the `register()` method (not just in `boot()`) to
  confirm the config value is actually available at binding time, not
  just later in the request lifecycle.
- For test-only wrong-resolution, check the base `TestCase` and any
  traits it uses for a global `bind()`/`singleton()` override, and check
  whether the failing test extends that base class unnecessarily.

## Fix
- Centralize interface-to-implementation bindings for a given
  interface in exactly one service provider (typically a dedicated
  `AppServiceProvider` section or a feature-specific provider), so there
  is one place to look and one place that can win -- avoid scattering
  `bind()` calls for the same abstract across multiple providers.
- Prefer contextual binding (`$this->app->when(...)->needs(...)->give(...)`)
  whenever more than one consumer needs different implementations of the
  same interface, instead of relying on plain `bind()` calls and load
  order to sort it out -- contextual binding makes the "who gets what"
  mapping explicit and independent of registration order.
- Move config-dependent conditional bindings into `boot()` rather than
  `register()` when the condition depends on config merged by another
  provider, since `boot()` runs after all providers have registered --
  or, if the binding itself must happen in `register()`, read the
  underlying config file/env value directly rather than depending on
  another provider having already finished its `register()` work.
- Scope test-only bindings to the specific test class or a narrowly-named
  trait applied only where needed, not a base `TestCase` that every test
  extends, so a fake implementation bound for one feature's tests can't
  leak into unrelated tests that expect the real one.

## Pitfalls
- "Fixing" this by binding the interface directly in the consuming
  class's constructor (`new StripeGateway()` instead of type-hinting the
  interface) removes the ambiguity but also removes the whole point of
  depending on an interface -- it defeats swappability for tests and
  future implementations; fix the binding, don't bypass the container.
- Reordering the `providers` array to "fix" the immediate bug is fragile
  -- the next new provider or package can silently re-break the order.
  Prefer contextual binding or a single source of truth for the binding
  over relying on array order as the mechanism.
- Binding as `singleton()` when the implementation actually needs
  per-request or per-call state (e.g. it holds a request-specific user
  context) causes stale state to leak across requests in long-running
  worker/octane processes -- match the binding lifetime (`bind` vs
  `singleton`) to the implementation's actual statefulness, not just
  whichever one happened to "work" in local testing with one request at
  a time.

## Verify
In `tinker`, resolve the interface in every context that matters (plain
`app(Interface::class)`, and inside an actual instance of each consuming
class via constructor injection through `app()->make(ConsumingClass::class)`)
and confirm each one reports the expected concrete class via
`get_class()`. For contextual bindings, add a unit test per consumer that
asserts the resolved implementation's class name, so a future duplicate
or reordered binding fails a test instead of silently swapping behavior
in production.
