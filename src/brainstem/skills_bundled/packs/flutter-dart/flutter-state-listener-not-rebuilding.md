---
name: flutter-state-listener-not-rebuilding
description: Diagnose a Provider, Riverpod, or Bloc state update that doesn't trigger a rebuild in a listening widget.
triggers: ["provider not rebuilding ui", "riverpod state changes but ui doesnt update", "blocbuilder not updating", "consumer not rebuilding flutter"]
permissions: ["READ"]
---

## Symptom
A widget wrapped in `Consumer`/`BlocBuilder`/`Selector`/`ref.watch` fails
to update its UI even though the underlying state provably changed
(confirmed via a print statement or breakpoint in the notifier), while
other parts of the app reading the same state elsewhere update correctly.

## Likely causes
1. **Mutating a field on an existing object in place** and calling
   `notifyListeners()`/`emit()` without ever creating a new instance -- if
   equality is reference-based (or an `Equatable` state's `props` doesn't
   change), the framework sees "no change" and skips notifying.
2. **Using `context.read<T>()` instead of `context.watch<T>()`** (or no
   `Consumer`/`Selector` at all) inside `build()`, so the widget never
   actually subscribes to change notifications.
3. **The provider is re-created rather than reused** -- e.g. a
   `ChangeNotifierProvider`/Riverpod provider declared inside a build
   method or under a separate `ProviderScope`, so the widget is listening
   to a different instance than the one being mutated.
4. **A Bloc/Cubit `Equatable` state missing a changed field in `props`**,
   so `state1 == state2` evaluates true and `BlocBuilder`'s rebuild logic
   (or a custom `buildWhen`) decides nothing changed.
5. **A `.family`/`autoDispose` Riverpod provider instantiated with
   different parameters** than expected, creating a distinct instance
   from the one the update is applied to.

## Diagnose
- Add logging inside the notifier's mutation method and inside the
  listening widget's `build()` to confirm both that the state actually
  changes and whether `build()` runs again afterward.
- For Bloc/Cubit, print `state` before and after the emit and check the
  state class's `props`/`==` override includes every field that changed.
- For Provider, use the widget inspector to check whether there are two
  separate provider instances in the tree rather than one shared
  instance.
- For Riverpod, confirm the widget uses `ref.watch(provider)` (not
  `ref.read`) inside `build`, and check for a `ProviderScope` override or
  a `.family` argument mismatch creating a distinct instance.

## Fix
- Always construct a new state object (or use `copyWith`) instead of
  mutating fields in place, then call `notifyListeners()`/`emit(newState)`
  with that new instance so identity/equality checks correctly detect the
  change.
- Replace `context.read<T>()` used for display with `context.watch<T>()`
  or wrap the relevant subtree in `Consumer<T>`/`BlocBuilder<T, S>` so a
  real subscription exists.
- Include every field that affects rendering in the Equatable state's
  `props`, or generate equality via `freezed` so it can't drift out of
  sync with the constructor's fields.
- Hoist provider creation to a stable point above the widgets that read
  it (e.g. above `MaterialApp`, or in `main()`) rather than inside a
  build method, so it isn't silently recreated on every parent rebuild.

## Pitfalls
- Blanket-replacing every `context.read` with `context.watch` "fixes" the
  bug but makes unrelated widgets rebuild too often -- only change the
  specific widget with the display problem.
- Forgetting to update `props` after adding a new field to a Bloc state
  class is an easy regression to reintroduce; prefer code generation
  (`freezed`) that derives equality from all constructor fields instead
  of a manually maintained list.

## Verify
Trigger the state change again and confirm, via DevTools rebuild
tracking or a `debugPrint` in the listening widget's `build()`, that
`build()` actually re-executes and the rendered UI reflects the new
value immediately, without requiring a hot reload or restart to catch up.
