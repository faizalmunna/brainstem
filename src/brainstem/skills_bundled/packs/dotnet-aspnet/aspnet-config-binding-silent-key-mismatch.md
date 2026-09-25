---
name: aspnet-config-binding-silent-key-mismatch
description: Diagnose an ASP.NET Core app that silently uses default values instead of failing at startup because an appsettings.json key doesn't match the options class.
triggers: ["options always have default values", "appsettings.json setting ignored", "iconfiguration binding not throwing on typo", "configuration section not applying", "settings work in one environment but not another silently"]
permissions: ["READ"]
---

## Symptom
A setting in `appsettings.json` (or `appsettings.{Environment}.json`,
environment variables, or a secrets store) appears to have no effect --
the bound options object always shows the C# default value for that
property instead of the configured value, and no exception, warning, or
log line indicates anything went wrong. This is especially dangerous when
it's a security-relevant or environment-specific setting (a timeout, a
feature flag, a connection string variant, a retry count) that silently
falls back to a default that happens to "work" well enough not to be
noticed immediately.

## Likely causes
1. **A typo or casing/nesting mismatch between the JSON key path and the
   options class's property names/section name** -- `IConfiguration`
   binding via `Configure<TOptions>(configuration.GetSection("MySetting"))`
   matches property names case-insensitively but still requires the
   section path and property names to line up exactly; a renamed property
   in code without updating `appsettings.json` (or vice versa) binds
   nothing for that property and leaves it at its C# default, with no
   error by default.
2. **The options are registered without validation** -- plain
   `Configure<TOptions>()` binds best-effort and does not fail startup
   for missing or extra keys; without `ValidateDataAnnotations()`,
   `ValidateOnStart()`, or a custom `IValidateOptions<TOptions>`, there is
   no mechanism that would ever surface a missing/misnamed key as an
   error.
3. **A key exists in one configuration source but is overridden (back to
   default) by a lower-precedence-looking source that's actually higher
   precedence** -- ASP.NET Core's configuration provider order means
   environment variables, command-line args, and user secrets can
   override `appsettings.{Environment}.json` depending on registration
   order; a value that looks correctly set in one file may be silently
   overridden elsewhere in the provider chain, mimicking a "binding
   didn't work" symptom.
4. **The section is bound twice under different names/paths** (e.g. once
   at the root and once nested), or bound to two different options types
   that don't share section names, so the code that reads the value reads
   the wrong bound instance (via `IOptions<T>` singleton snapshot) while
   the configuration file's actual value lives in a section nobody
   reads from.

## Diagnose
- Log the fully bound options object at startup (a targeted diagnostic
  log, not left in permanently) and compare every property's actual value
  against what's expected from `appsettings.json` -- any property still
  showing a C# default when the file specifies something else is a
  binding miss.
- Grep `appsettings.json` and all environment-specific variants for the
  exact section/key path used in `GetSection("...")` calls in code --
  confirm the path segments and casing match exactly (`ConfigA:SubB` in
  code must correspond to `"ConfigA": { "SubB": ... }` in JSON).
- Add `.ValidateDataAnnotations().ValidateOnStart()` (or an
  `IValidateOptions<TOptions>` implementation) temporarily to the
  affected options registration and restart the app -- if a required
  property is unexpectedly still at its default because the key never
  bound, an explicit validation failure at startup will confirm which
  property and often why.
- Dump the effective merged configuration at startup with
  `((IConfigurationRoot)configuration).GetDebugView()` -- this shows
  every key, its resolved value, and which provider (which file, env var,
  etc.) it came from, immediately revealing both misnamed keys (absent
  from the tree) and unexpected overrides (present but from the wrong
  provider).

## Fix
- Make configuration binding fail loudly instead of silently: register
  options with `.Bind(configuration.GetSection("Section"), o =>
  o.ErrorOnUnknownConfiguration = true)` where available, and always pair
  `Configure<TOptions>()` with `ValidateDataAnnotations()` and
  `ValidateOnStart()` so required fields missing or misbound cause
  startup to fail with a specific, actionable exception instead of
  running with silent defaults.
- Add data annotations (`[Required]`, `[Range]`, etc.) or a custom
  `IValidateOptions<TOptions>` to every options class that has a setting
  where a silent default would be dangerous (timeouts, connection
  strings, feature toggles affecting security), so a misnamed key
  surfaces as a startup failure rather than a runtime surprise.
- Use strongly-typed configuration section constants (a `const string
  SectionName` on the options class itself, referenced both by the
  registration code and, where possible, documented next to the JSON) to
  reduce the chance of the section path and the JSON structure drifting
  apart silently during a rename.
- Use `GetDebugView()` (or equivalent) as a standard part of startup
  diagnostics/health checks in non-production environments so a
  misconfigured deploy is visible in logs immediately rather than
  discovered later from a wrong runtime behavior.

## Pitfalls
- Adding validation only in `Development` and not `Production`
  configuration means the exact silent-default risk this fix addresses
  still exists in the environment where it matters most -- register
  `ValidateOnStart()` unconditionally, not gated behind an environment
  check, so a bad production deploy fails to start rather than starting
  with wrong defaults.
- Over-validating with overly strict `[Required]` on genuinely optional
  settings breaks legitimate deployments that rely on the C# default on
  purpose -- distinguish "this must be explicitly configured" properties
  from "this has a sensible default" properties rather than requiring
  every field.

## Verify
Deliberately misname or remove the previously-broken key from
`appsettings.json` in a test/staging deploy after adding validation, and
confirm the application now fails fast at startup with a clear exception
naming the missing/invalid option, rather than starting successfully and
silently using the default -- then restore the correct key and confirm
clean startup with the expected bound value present in the logged/dumped
configuration.
