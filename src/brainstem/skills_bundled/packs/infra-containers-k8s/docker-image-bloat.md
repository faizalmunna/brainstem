---
name: docker-image-bloat
description: Diagnose and reduce an unexpectedly large Docker image, which slows deploys, increases attack surface, and wastes registry storage/bandwidth.
triggers: ["docker image too big", "reduce docker image size", "slow docker push pull", "docker image bloat", "multi-stage build"]
permissions: ["READ"]
---

## Symptom
A Docker image is significantly larger than expected for what the
application actually needs at runtime, causing slow builds/pushes/pulls,
slower deploys/autoscaling (larger images take longer to pull onto new
nodes), and unnecessary attack surface from unused packages.

## Likely causes
1. **Build-time dependencies shipped in the final image** -- compilers,
   build tools, dev dependencies, and source files that were only needed
   to produce build artifacts, not to run them, but weren't excluded from
   the final stage.
2. **No multi-stage build** -- a single-stage Dockerfile that installs
   everything (build tools included) into the same image that gets
   deployed, rather than building in one stage and copying only the
   runtime artifacts into a clean final stage.
3. **A large base image** chosen for convenience (a full OS image) when a
   slimmer or distroless base would suffice for the actual runtime
   requirements.
4. **Poor layer caching/ordering** causing large layers to be
   unnecessarily duplicated across image versions (not a size problem
   for a single image, but a bandwidth/storage problem across many
   versions), or a `COPY . .` early in the Dockerfile invalidating cached
   dependency-install layers on every code change.
5. **Unnecessary files included via a missing/incomplete `.dockerignore`**
   -- `.git` history, local `node_modules`, build artifacts from the host,
   test fixtures, or documentation copied into the image unintentionally.

## Diagnose
- `docker history <image>` (or `docker scout`/`dive`) to see each layer's
  size and identify which step contributes the most bloat.
- Check the Dockerfile for a multi-stage pattern (`FROM ... AS build`
  followed by a second `FROM` that copies only specific artifacts) versus
  a single stage that installs everything.
- Check the base image tag: a full distribution (`ubuntu:latest`,
  `node:20`) versus a slim/alpine/distroless variant, and whether the
  extra packages the full image provides are actually used at runtime.
- Check for a `.dockerignore` file and whether it excludes `.git`,
  `node_modules`, test directories, and other build-host-only files.

## Fix
- Adopt a multi-stage build: install build tools and compile/build in an
  early stage, then `COPY --from=build` only the compiled
  artifacts/runtime dependencies into a fresh, minimal final stage that
  never had the build tools installed in the first place.
- Choose the smallest base image that meets actual runtime requirements
  (slim/alpine variants, or distroless images for compiled languages that
  don't need a shell/package manager at runtime at all), verifying the
  application's actual dependencies (some native modules need glibc,
  ruling out alpine without extra work) before switching.
- Add/expand `.dockerignore` to exclude `.git`, local dependency
  directories that get reinstalled inside the build anyway, test
  fixtures, and documentation.
- Order Dockerfile instructions so infrequently-changing steps (installing
  dependencies from a lockfile) come before frequently-changing steps
  (copying application source), so cache invalidation from a code change
  doesn't force a full dependency reinstall on every build.

## Pitfalls
- Switching to alpine/distroless without testing can break native
  dependencies that expect glibc (many compiled Python/Node native
  modules) -- verify the application actually runs correctly on the
  slimmer base before adopting it, not just that the build succeeds.
- Multi-stage builds can accidentally still copy more than intended
  (`COPY --from=build /app /app` copying the build stage's node_modules
  including devDependencies) -- be explicit about exactly which
  artifacts/directories are copied into the final stage.
- Removing packages "not needed at runtime" without checking transitive
  runtime dependencies (a shared library another package silently needs)
  can break the application in ways only visible when a specific code
  path executes, not at build/smoke-test time.

## Verify
Compare `docker images` size before and after, and run the application's
full test/smoke-test suite against the new, smaller image (not just
confirm it starts) to catch any runtime dependency that was
inadvertently removed.
