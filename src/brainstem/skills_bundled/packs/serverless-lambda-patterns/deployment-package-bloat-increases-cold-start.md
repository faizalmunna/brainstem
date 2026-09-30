---
name: deployment-package-bloat-increases-cold-start
description: A function's deployment package grows large enough from unnecessary bundled dependencies to meaningfully increase cold-start latency.
triggers: ["lambda cold start got slower after deploy", "large deployment package slow lambda", "function bundle size increasing latency", "lambda init duration increased"]
permissions: ["READ"]
---

## Symptom
Cold-start latency (the platform's reported init duration, or
time-to-first-byte on a cold invocation) has crept up over successive
deploys with no corresponding change to the function's actual business
logic. The function still works correctly, but p99 latency for cold
invocations is now noticeably worse than it was months ago, users
occasionally notice a multi-second delay on the first request after a
period of inactivity, and nobody made one single change that looks like
the obvious cause.

## Likely causes
1. **The deployment package bundles an entire dependency tree instead of
   just what the code actually imports** -- a package manager's default
   install behavior pulls in every transitive dependency including large
   ones (an entire cloud SDK, a full data-processing library) even when
   the code only uses a small corner of it, and package size grows quietly
   with every dependency added over time without anyone auditing it.
2. **Build tooling isn't tree-shaking or minifying**, so dev-only tooling,
   unused exports, source maps, test fixtures, or documentation files
   inside `node_modules`/site-packages/vendor directories get bundled into
   the deployed artifact even though they're never executed.
3. **A large dependency was added for a narrow use case** (e.g., pulling
   in a full ORM or full cloud SDK just to call one API) when a lighter
   client or a single targeted import would have sufficed, and the
   dependency's size cost was never weighed against the alternative at
   the time it was added.
4. **The runtime has to unpack/initialize a larger package on cold start**
   -- for languages where import/require time scales with the amount of
   code being loaded (importing an entire large module eagerly rather than
   lazily), a bigger package means more time spent in language-level
   module initialization before the handler even runs, on top of any
   platform-level package download/mount overhead.
5. **Container-image-based functions accumulate layers of build artifacts
   that aren't actually needed at runtime** (build-time compilers, dev
   dependencies, cached package manager files) because the image wasn't
   built with a multi-stage build that discards everything except the
   final runtime artifact.

## Diagnose
- Compare the deployed package/image size over time against deploy
  history (via the platform's console/API, or by tracking artifact size
  in CI) to confirm size has actually grown and correlate the growth with
  specific dependency-adding commits, rather than assuming a cause.
- Check the platform's cold-start/init-duration metric over the same time
  range and confirm it trends upward alongside package size, not just
  once but as a sustained trend -- ruling out a one-off spike from an
  unrelated infrastructure event.
- Inspect the actual contents of the deployment package (unzip it, or list
  a container image's layers) and identify the largest individual
  directories/files -- most bloat concentrates in a small number of large
  dependencies or accidentally-included build artifacts, not evenly across
  everything.
- For each large dependency found, grep the function's actual source code
  for what portion of that dependency's API is actually imported/used --
  a dependency where only one small module is used out of a much larger
  package is a strong candidate for replacement with a lighter
  alternative or a scoped import.
- Check whether the language runtime supports lazy/on-demand imports
  inside the handler versus eager imports at module scope -- code that
  eagerly imports a large module it only sometimes needs pays that
  import's full cold-start cost on every cold start, even for invocations
  that never use it.

## Fix
Audit and prune the dependency tree deliberately: remove dependencies that
are unused or only marginally used, replace heavy general-purpose
libraries with lighter single-purpose alternatives where only a small
slice of functionality is needed, and exclude dev-only tooling, test
fixtures, and source maps from the deployed artifact via the build
tool's packaging configuration. Use tree-shaking/minification where the
runtime and build tooling support it, and for container-image-based
functions, use multi-stage builds so the final image contains only
runtime-necessary files, not build-time compilers or caches. Where the
platform supports layers/shared dependency mechanisms (Lambda layers, a
shared base image), move large, slow-changing dependencies into a
separately cached layer rather than rebundling them into every deploy of
the function's own code, which can also reduce the actual artifact that
needs to move on each deploy. Where a dependency is only needed for one
rarely-used code path, import it lazily inside the specific handler branch
that uses it rather than at module scope.

## Pitfalls
Chasing package size reduction as an end in itself can lead to manually
vendoring stripped-down forks of dependencies, which trades a
cold-start-latency problem for a maintenance and security-patching
problem (the vendored code stops receiving upstream fixes) -- prefer
removing genuinely unused dependencies and scoping imports over
hand-trimming ones still in active use. Also, moving a large dependency
into a Lambda layer doesn't eliminate its cold-start cost by itself --
the runtime still has to load/import it during cold start; layers mainly
help with deployment artifact size and reuse across functions, not with
import-time cost, so don't treat "move it to a layer" as a complete fix
for slow module initialization.

## Verify
Measure cold-start init duration before and after the pruning, using a
forced cold start (e.g., updating an environment variable to invalidate
warm containers) run several times to get a stable sample rather than a
single measurement, and confirm both the deployment package size and the
p50/p99 init duration have measurably decreased; also confirm the
function's full test suite still passes to ensure no functionality was
lost in removing dependencies.
