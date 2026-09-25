---
name: before-action-leaks-to-unintended-action
description: Fix a before_action filter that unexpectedly runs on a controller action it was never meant to guard, due to inheritance.
triggers: ["before_action running on wrong action", "authorization filter fires on unintended action", "before_action inherited unexpectedly", "controller filter runs for new action automatically", "skip_before_action not working"]
permissions: ["READ"]
---

## Symptom
A newly added (or newly renamed) controller action unexpectedly gets
redirected, 403s, or runs extra setup logic that no other similar action
runs -- tracing it back shows a `before_action` defined in a parent
controller (often `ApplicationController` or a feature-specific base
controller) is firing for this action even though nothing in the
subclass's own file appears to reference it.

## Likely causes
1. **`before_action` in a shared/base controller has no `only:`/`except:`
   restriction**, so it applies to every action in every subclass by
   default -- a new action added to a subclass automatically inherits it,
   which is correct Rails behavior but surprising if the filter was
   originally written with only the base controller's own actions in
   mind.
2. **A `skip_before_action` in the subclass targets the wrong filter name
   or the wrong action list** -- e.g. the base controller's filter method
   was renamed or the skip was written against an old action name,
   silently becoming a no-op (Rails raises `ArgumentError` for skipping
   an unregistered filter only in some configurations; it can silently no-op
   in others depending on `raise: false`).
3. **Controller inheritance is deeper than expected** -- the action's
   controller inherits from an intermediate controller (e.g.
   `Admin::BaseController < ApplicationController`) that itself adds
   another `before_action`, and the developer only checked the immediate
   parent, missing a filter added two levels up.
4. **The filter is added via a module/concern included in the base
   controller**, making it non-obvious from reading the base controller's
   own file that the filter exists at all -- especially if the concern is
   included conditionally or the `before_action` call is inside the
   concern's `included do ... end` block.

## Diagnose
- In a console or via `rails routes`/a debugger, inspect the actual
  filter chain for the specific controller and action:
  `SomeController._process_action_callbacks.map { |cb| [cb.kind, cb.filter] }`
  lists every callback, in order, including inherited ones -- this shows
  exactly which filter fires and from where.
- Trace the controller's full ancestry (`SomeController.ancestors`) to
  find every class and module between it and `ActionController::Base`,
  then check each one for `before_action` calls, not just the immediate
  parent.
- If a `skip_before_action` is already present, confirm the filter name
  matches exactly (including if it's a method vs. a named proc) and that
  the action list (`only:`/`except:`) includes the action currently
  misbehaving -- a typo'd action name silently fails to skip it.
- Add a temporary `Rails.logger.debug` at the top of the suspected filter
  method printing `action_name` and `self.class` to confirm, at runtime,
  which controller/action combination is triggering it.

## Fix
- Scope shared `before_action`s in base controllers explicitly with
  `only:`/`except:` whenever the filter is meant for a subset of actions,
  rather than relying on every subclass to remember to skip it -- inverting
  the responsibility from "each subclass must opt out" to "the filter
  declares its own intended scope" prevents the leak for every future
  action added anywhere in the hierarchy.
- When a specific subclass genuinely needs to opt out, use
  `skip_before_action :filter_name, only: [:action_name], raise: false`
  during the transition, then remove `raise: false` once confirmed correct,
  so a future filter-name typo raises loudly instead of silently no-op'ing.
- For filters added via an included concern, keep the `before_action` call
  visible and grep-able (avoid conditionally including it inside deeply
  nested `if`/`case` logic in `included do` blocks) so a controller's
  actual filter chain can be understood by reading the controller and its
  documented concerns, not by tracing runtime behavior.
- Consider whether the new action actually belongs in this controller at
  all -- if it has fundamentally different authorization/setup needs than
  its siblings, a new, more narrowly-scoped controller (or namespace) may
  be a better fix than accumulating skips.

## Pitfalls
- Reflexively adding `skip_before_action` to make a new action work
  without understanding *why* the filter runs risks skipping something
  load-bearing (an authorization check) rather than a genuinely
  unnecessary setup step -- always identify what the filter does before
  deciding to skip it.
- Scoping a base controller's filter with `except:` listing every current
  action that shouldn't run it is fragile -- a newly added action is
  automatically included by default (the risky direction), whereas
  scoping with `only:` naming the actions that *should* run it fails safe
  for new actions instead.
- Forgetting that `skip_before_action` must match the *exact* registration
  (same method/proc, same controller in the chain) -- skipping a
  same-named filter defined differently in a different module silently
  does nothing.

## Verify
Write a controller/request spec for the specific new action that asserts
the filter's *absence* of effect directly (e.g. the action succeeds
without the authorization condition the filter would have enforced, for
a case where it legitimately shouldn't apply), and a separate spec
confirming the filter still fires correctly for the actions it's meant to
guard. Also re-run `_process_action_callbacks` for the affected controller
and action to confirm the filter chain now matches intent.
