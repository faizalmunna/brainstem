---
name: spring-profile-config-not-active-in-deployment
description: A Spring profile-specific configuration (application-prod.yml, a @Profile-annotated bean) is silently ignored in a deployed environment, and the application runs with default/dev settings instead.
triggers: ["spring profile not active", "wrong config loaded in production", "application-prod.yml ignored", "profile bean not registered", "spring.profiles.active not working"]
permissions: ["READ"]
---

## Symptom

An application deployed to a specific environment (staging, production)
behaves as if it's still running with development defaults -- pointing at
a local database, using verbose logging, missing a `@Profile("prod")`
bean entirely -- even though `application-prod.yml` (or the equivalent
profile-specific config) exists and looks correct.

## Likely causes

- **`spring.profiles.active` was never actually set in the deployment
  environment** -- it was set correctly in a local `.env` file or IDE run
  configuration that doesn't carry over to the deployed process (a
  container, a systemd service, a cloud platform's environment variables).
- **The property was set via the wrong mechanism for how the app was
  started** -- e.g. set as a JVM system property (`-Dspring.profiles.
  active=prod`) but the process was actually started with a different
  command that doesn't pass it, or set in `application.yml` itself in a
  way that gets overridden by a blank environment variable.
- **A typo or case mismatch in the profile name** (`Prod` vs `prod`,
  or `production` in the filename but `prod` in the activation config)
  causes Spring to look for a profile that doesn't match any file.
- **Multiple configuration sources conflict**, with a lower-precedence
  source's `spring.profiles.active` value unexpectedly winning due to
  Spring's property-source precedence order not being what was assumed.
- **The profile is activated correctly, but a `@Profile`-annotated bean's
  condition doesn't match** because of how profile expressions combine
  (e.g. `@Profile("!dev")` behaving unexpectedly alongside another active
  profile).

## Diagnose

1. Check the actual running application's active profiles directly --
   the Spring Boot Actuator `/actuator/env` endpoint (if enabled) shows
   `spring.profiles.active` as actually resolved at runtime, which is
   more reliable than reading deployment config and assuming it applied.
2. Check application startup logs for Spring's own log line reporting
   "The following profiles are active: ..." (or "No active profile set,
   falling back to default profiles") near the start of the log.
3. Trace exactly how the deployment starts the process (Dockerfile
   `ENTRYPOINT`/`CMD`, systemd unit file, cloud platform's configured
   start command/environment variables) and confirm the profile-setting
   mechanism used there matches what's actually expected.
4. If a specific bean seems missing, check its `@Profile` expression
   against the full list of profiles actually active (not just the one
   you expected) -- combinations can behave differently than a single
   profile in isolation.

## Fix

Set `spring.profiles.active` through the mechanism that's actually
guaranteed to reach the deployed process -- typically an environment
variable (`SPRING_PROFILES_ACTIVE`) set directly in the deployment
platform's configuration (container orchestrator, PaaS environment
variables), rather than relying on a config file that may or may not be
picked up depending on classpath/working-directory assumptions. Verify
the exact string match between the profile name used to activate it and
the filename suffix (`application-<profile>.yml`) -- Spring profile names
are case-sensitive strings, not a fuzzy match. For multi-profile setups,
explicitly test the actual combination that will run in each real
environment rather than assuming individual profiles compose the way
they're expected to.

## Pitfalls

Don't "fix" this by hardcoding environment-specific values directly into
`application.yml` to bypass the profile system entirely -- that
reintroduces the exact problem profiles exist to solve (the same artifact
behaving differently, or needing manual editing, per environment). Also
don't assume a missing profile silently falls back to safe defaults --
depending on what's profile-gated, a missing profile can mean a critical
bean (a real database connection, a required security filter) simply
doesn't exist at all, which can fail open rather than obviously erroring.

## Verify

After fixing the activation mechanism, check `/actuator/env` (or
equivalent) on the actual deployed instance and confirm the expected
profile(s) show up in `activeProfiles`, and confirm the specific
previously-missing profile-gated bean/behavior is now present. Redeploy
once more from a clean state (not just restart) to confirm the fix
survives the actual deployment process, not just a manually patched
running instance.
