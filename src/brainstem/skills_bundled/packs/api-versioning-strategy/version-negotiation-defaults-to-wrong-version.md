---
name: version-negotiation-defaults-to-wrong-version
description: A client that doesn't explicitly specify an API version silently receives a different version than expected because the server's default-version behavior changed or was ambiguous.
triggers: ["client got wrong api version by default", "default api version changed unexpectedly", "no version specified got unexpected behavior", "implicit version negotiation broke client"]
permissions: ["READ"]
---

## Symptom

A client that never explicitly specifies an API version (relying on
whatever the server treats as the default) starts receiving different
behavior or response structure than before, without the client making
any change on its own side -- the server's notion of "default version"
shifted underneath it.

## Likely causes

- **The server's default version was changed as part of releasing a new
  version** (making the newest version the default going forward), with
  the assumption that clients should always want the latest, without
  considering that unversioned clients were implicitly depending on the
  previous default's specific behavior.
- **No explicit contract exists for what happens when a client doesn't
  specify a version**, so "default" behavior was never a deliberate,
  documented decision -- it was just whatever the server happened to do,
  making it liable to change unintentionally as the codebase evolves.
- **Different parts of the API (different endpoints, or different
  layers like a gateway versus the backend service) have inconsistent
  default-version logic**, so a client hitting different endpoints
  without specifying a version gets inconsistent behavior across them.
- **A client library or SDK was supposed to always specify a version
  explicitly but had a bug or configuration gap causing it to omit the
  version parameter in some code paths**, making the client
  unintentionally dependent on server-side default behavior it never
  meant to rely on.

## Diagnose

1. Confirm whether the specific client actually sends a version
   parameter/header on its requests, or relies on the server's default,
   by inspecting actual request traffic.
2. Check the server's version-negotiation logic for what it currently
   treats as default, and compare against what it treated as default
   before the change that caused the symptom.
3. Check whether default-version behavior is documented anywhere as an
   explicit contract, or whether it's undocumented, implicit behavior.
4. If multiple layers (gateway, backend) are involved, check each layer's
   own version-defaulting logic for consistency.

## Fix

Require every client to explicitly specify an API version on every
request, treating "no version specified" as an error condition (or, at
minimum, a logged warning) rather than silently falling back to a
default that can change over time. If defaulting is genuinely required
for backward compatibility with existing unversioned clients, pin the
default to the specific version those clients were built against and
treat changing that default as itself a breaking change requiring the
same deprecation process as any other breaking change -- never change
what "default" means without the same notice period as an explicit
version sunset.

## Pitfalls

Don't assume defaulting to "latest" is always the safest choice for
unversioned clients -- it's actually the opposite, since it means
unversioned clients' behavior changes every time a new version ships,
which is the least predictable possible default; a pinned, stable default
that only changes with an explicit, communicated migration is safer.

## Verify

Confirm the API now rejects (or clearly warns on) requests missing an
explicit version, or confirm the default version is now explicitly
documented and pinned rather than implicitly tied to "whatever's
newest." Test an unversioned request and confirm it receives the
documented, stable default behavior consistently across releases.
