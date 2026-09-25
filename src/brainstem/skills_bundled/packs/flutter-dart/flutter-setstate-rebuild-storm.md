---
name: flutter-setstate-rebuild-storm
description: Diagnose an entire widget subtree rebuilding on every state change because setState was called too high in the tree.
triggers: ["setstate rebuilds everything", "whole screen rebuilds on tiny state change", "flutter rebuilding too much", "why does my whole page redraw"]
permissions: ["READ"]
---

## Symptom
Toggling one small piece of state (a checkbox, a counter, a selected tab)
causes a wide swath of unrelated widgets -- headers, list items, sibling
cards -- to rebuild too, visible as a burst of highlighted widgets in
Flutter DevTools' rebuild tracking every time the state changes, even
though only one leaf widget's rendered output actually changed.

## Likely causes
1. **`setState()` is called inside a StatefulWidget positioned high in the
   tree** (e.g. the widget wrapping the whole `Scaffold` body), so its
   entire `build()` method reruns and every non-const child is rebuilt
   along with it.
2. **A mutable value is threaded down through many widget constructors**
   instead of being scoped with `InheritedWidget`/`Provider`/`Riverpod`,
   so any change forces a rebuild starting from wherever the value is
   held, cascading to everything beneath it.
3. **Missing `const` constructors** on child widgets that don't actually
   depend on the changing state, so Flutter has no way to know it can
   skip them during the ancestor's rebuild.
4. **A single large `ChangeNotifier`/Bloc state object** emitting the
   whole object on any field change, so every listener rebuilds
   regardless of which specific field it reads.

## Diagnose
- Enable "Track widget builds" in Flutter DevTools' Performance view,
  trigger the state change, and note every widget that flashes as
  rebuilt versus the one that should have.
- Set `debugPrintRebuildDirtyWidgets = true;` (from
  `package:flutter/rendering.dart`) temporarily and trigger the change --
  the console lists every widget marked dirty for that frame.
- Grep for `setState(` and check the enclosing StatefulWidget's position
  in the tree -- if it wraps a large section of UI, that's the rebuild
  boundary.
- Confirm sibling/cousin widgets with no logical dependency on the
  changed state are appearing in the same rebuild batch.

## Fix
- Push the state and its `setState` call down into the smallest
  StatefulWidget (or a narrowly scoped `Consumer`/`Selector`/
  `BlocBuilder`) that actually needs to react to it, so the rebuild
  boundary matches the visual change, not the whole screen.
- Add `const` constructors to every widget that doesn't depend on the
  changing state -- Flutter skips rebuilding const subtrees entirely
  during an ancestor's rebuild.
- Wrap expensive, independent subtrees in `RepaintBoundary` so painting
  is isolated even when a rebuild is still triggered.
- Use fine-grained watchers (Riverpod's `select`, Provider's `Selector`,
  Bloc's `buildWhen`) so a listener declares exactly which field(s) it
  cares about instead of rebuilding on any change to the whole model.

## Pitfalls
- Marking widgets `const` further down the tree does nothing if a single
  non-const ancestor still recreates their constructor arguments every
  build -- the const-ness has to hold for the actual widget instance
  being compared, not just be present somewhere in the file.
- Over-splitting into many tiny StatefulWidgets to chase this fix can
  fragment state and complicate `initState`/`dispose` lifecycle
  management -- profile first to confirm rebuild scope is the actual
  bottleneck before restructuring broadly.

## Verify
Re-run DevTools rebuild tracking after the change: triggering the same
state update should now highlight only the intended leaf widget(s), with
previously-flashing ancestors and siblings no longer appearing in that
frame's rebuild list.
