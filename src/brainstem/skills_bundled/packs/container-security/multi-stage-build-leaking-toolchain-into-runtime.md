---
name: multi-stage-build-leaking-toolchain-into-runtime
description: A multi-stage Docker build accidentally ships compilers, package managers, and source code into the final runtime image instead of only the built artifact.
triggers: ["why is our production image 1.2gb when the app is 20mb", "final image still has gcc and npm installed", "runtime container has build tools we don't need in prod"]
permissions: ["READ"]
---

## Symptom
The final, deployed image is far larger than the compiled/built artifact should require (hundreds of MB to multiple GB for what should be a small binary or bundled app), and inspecting it (`docker exec <container> which gcc npm pip`) reveals a full compiler toolchain, package manager, or source tree still present in the image that's actually running in production. This is a security surface issue as much as a size issue: every extra tool is something a compromised process could use (compilers to build exploit tooling, package managers to pull in additional payloads, shells and debug utilities to explore and pivot).

## Likely causes
1. **The Dockerfile uses only a single stage** -- `FROM node:18` (or similar full SDK image) all the way through, installing build dependencies, building the app, and running it from the same image, with no separation between "what's needed to build" and "what's needed to run."
2. **A multi-stage build exists but the final `COPY --from=builder` step copies too much** -- copying an entire `/app` directory that still contains `node_modules` dev dependencies, `.git`, source `.ts` files alongside compiled `.js`, or the whole build cache, instead of copying only the specific built output directory.
3. **The final stage's base image is still a full SDK/dev image** (e.g. `FROM node:18` instead of `FROM node:18-slim` or `gcr.io/distroless/nodejs`) even though a build stage already exists -- the separation of build vs. runtime *stages* was done, but the runtime *stage's base image* wasn't correspondingly minimized.
4. **Debugging tools were added to the runtime stage "temporarily"** (curl, vim, a shell, netcat) to troubleshoot an issue in production and never removed once the immediate problem was solved.

## Diagnose
1. Compare the expected artifact size to the actual image size: `docker images myimage:tag` vs. the known size of the compiled binary/bundle -- a large multiple (10x+) signals bloat.
2. Enumerate what's actually present: `docker run --rm myimage:tag sh -c "which gcc cc make npm pip git curl wget vim 2>/dev/null"` -- anything that returns a path but isn't required at runtime is a candidate for removal.
3. Inspect the Dockerfile for stage boundaries: confirm there are at least two `FROM` statements (builder and runtime) and that the final stage's `FROM` is a minimal base, not the same SDK image used to build.
4. Check exactly what the final `COPY --from=` line copies -- if it's a directory rather than a specific named artifact/binary/dist folder, it's likely over-including build-time files.

## Fix
Structure the Dockerfile as a genuine multi-stage build: an early stage with the full SDK/toolchain to compile or bundle the application, and a separate final stage `FROM` a minimal runtime base (a slim variant, or a distroless image where the language runtime supports it) that only `COPY --from=builder` the specific compiled output -- a single binary, a `dist/` folder, or production-only `node_modules` installed fresh in that stage rather than copied from the builder. Remove any debugging tools from the runtime stage; if interactive debugging is occasionally needed, use ephemeral debug containers (`kubectl debug` with a separate debug image) attached to the running pod instead of permanently bundling those tools into the production image.

## Pitfalls
Switching to a distroless or scratch-based final image without first confirming the application has no runtime dependency on a shell or standard libc utilities (health check scripts that call `sh`, entrypoint wrapper scripts, dynamic linking against glibc when the base uses musl) causes the container to fail to start with a cryptic "no such file or directory" error that has nothing to do with the actual missing file -- verify the binary's dynamic linking and any shell dependencies before switching base images, not after.

## Verify
After restructuring, confirm the final image size dropped to roughly the expected order of magnitude for the artifact (`docker images`), and confirm the toolchain is actually gone: `docker run --rm myimage:tag sh -c "which gcc npm pip git" 2>&1` should report not-found (or the shell itself should be absent if using distroless, in which case confirm via `docker inspect` that no shell entrypoint is required). Finally, run the full application test suite against the new minimal image to confirm nothing implicitly depended on a now-removed tool.
