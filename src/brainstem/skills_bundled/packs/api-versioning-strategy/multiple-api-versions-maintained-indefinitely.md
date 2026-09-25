---
name: multiple-api-versions-maintained-indefinitely
description: An API accumulates several concurrently supported versions over time because none are ever deprecated and removed, multiplying maintenance burden and bug surface indefinitely.
triggers: ["too many api versions maintained", "old api version never deprecated", "api version sprawl", "cannot retire old api version"]
permissions: ["READ"]
---

## Symptom

An API has accumulated three, four, or more concurrently supported
versions over its lifetime, each requiring ongoing maintenance
(bug fixes, security patches, infrastructure updates applied across all
versions) -- and none has ever actually been deprecated and removed,
because "some client might still be using it" is always cited as a
reason to keep it indefinitely.

## Likely causes

- **A formal deprecation and sunset process was never established**, so
  each new version is added without a corresponding plan or commitment to
  eventually retire an old one, making version count purely additive
  over time.
- **Nobody has visibility into which clients actually use which version**,
  so there's genuine uncertainty about whether retiring an old version
  would break anyone, and that uncertainty defaults to indefinite
  preservation rather than active investigation.
- **The organizational cost of maintaining old versions isn't tracked or
  made visible** (engineering time spent patching multiple versions, the
  complexity cost in the codebase), so there's no concrete pressure
  driving deprecation decisions.
- **Communicating a deprecation timeline to external clients feels
  risky or effortful** (potential support burden, client relationship
  concerns), so it's easier to avoid the conversation and keep
  maintaining everything indefinitely.

## Diagnose

1. Inventory all currently supported API versions and, for each, measure
   actual usage (request volume, number of distinct clients) via access
   logs or API gateway metrics.
2. Calculate the actual engineering cost of maintaining each version
   (time spent on version-specific bug fixes, infrastructure, testing)
   to make the maintenance burden concrete rather than assumed.
3. For versions with genuinely low or zero usage, identify the specific
   remaining clients (if any) and assess what it would take to migrate
   them.
4. Check whether any deprecation communication or sunset process exists
   at all, or whether every version has simply been kept by default.

## Fix

Establish an explicit deprecation policy (a defined support window per
version, a required migration notice period) and apply it retroactively
to currently unbounded old versions -- announce a sunset date for
low-usage versions, provide migration guides, and directly reach out to
identified remaining clients on old versions with a clear timeline.
Build usage monitoring per API version as a standing practice so future
deprecation decisions are based on real data rather than assumption.
Make the maintenance cost of old versions visible in planning
discussions, so the tradeoff of keeping a version alive is weighed
explicitly rather than defaulted to.

## Pitfalls

Don't deprecate and remove an old version abruptly without adequate
notice and a real migration path, even if usage looks low -- a
low-but-nonzero usage count still represents real clients who'll be
broken with no warning; always provide a defined notice period and
direct outreach to identified users before actually removing a version.

## Verify

Confirm the deprecation policy is documented and applied to at least one
previously-indefinite old version, with a concrete sunset date
communicated to remaining users. After the sunset date passes, confirm
the old version's actual usage has dropped to zero (or migrated users
have been individually handled) before fully decommissioning it.
