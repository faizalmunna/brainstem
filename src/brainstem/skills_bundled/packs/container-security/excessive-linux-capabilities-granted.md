---
name: excessive-linux-capabilities-granted
description: A container runs with the full default Linux capability set or extra added capabilities that its process never actually exercises, widening what a compromised process can do.
triggers: ["should we drop linux capabilities from this container", "cap_sys_admin granted but not used", "security scan flags excessive capabilities on container"]
permissions: ["READ"]
---

## Symptom
An audit tool or manual `docker inspect`/pod spec review shows a container running with Docker's full default capability set (roughly 14 capabilities including `NET_RAW`, `CHOWN`, `SETUID`, `SETGID`, etc.) or with extra capabilities explicitly added (`CAP_SYS_ADMIN`, `CAP_NET_ADMIN`), but the application is an ordinary service (web server, API, worker) that doesn't perform raw networking, doesn't change file ownership at runtime, and doesn't need kernel-level administrative access. This is distinct from running as root -- capabilities are granted per-process regardless of UID and independently widen what a compromised process, even a non-root one, can do.

## Likely causes
1. **Nobody ever ran `--cap-drop=ALL` and added back only what's needed** -- Docker's default capability set is applied uniformly to every container regardless of whether the workload uses any of it, because dropping and re-adding requires knowing exactly which capabilities the app needs, which is extra diagnostic work most teams skip.
2. **A capability was added to solve one specific problem (e.g. `CAP_NET_BIND_SERVICE` to bind a low port, or `CAP_SYS_PTRACE` for a debugging session) and was never removed after the underlying need went away or was solved differently.**
3. **A dependency or base tool bundled into the image nominally "needs" broad capabilities for some rarely-used code path** (e.g. a full ping/traceroute utility needing `CAP_NET_RAW`) that the application itself never invokes, so the capability is granted for functionality that isn't even in use.
4. **Kubernetes `securityContext.capabilities` isn't configured at all**, so pods inherit the container runtime's default set with no explicit `drop`/`add` list, meaning nobody has actually reasoned about what this specific workload needs.

## Diagnose
1. Inspect current effective capabilities on a running container: `docker inspect <container> --format '{{.HostConfig.CapAdd}} {{.HostConfig.CapDrop}}'`, or from inside the container, `capsh --print` (or `getpcaps 1`) to see the actual effective set for the main process.
2. For Kubernetes, check `kubectl get pod <pod> -o jsonpath='{.spec.containers[0].securityContext.capabilities}'` -- an empty/absent field means the runtime default (not `ALL` dropped) is in effect.
3. Trace which capabilities the process actually uses under normal operation with `strace -f -e trace=%process,capset <pid>` or by testing with `--cap-drop=ALL` in a staging environment and observing exactly which syscalls fail with `EPERM`, which pinpoints the minimum needed set empirically rather than by guesswork.
4. Cross-reference any explicitly added capability against the actual code path that needs it -- if `CAP_SYS_ADMIN` was added for a mount operation that happens once at container init via an init container or entrypoint script, it likely doesn't need to persist on the long-running main process.

## Fix
Start from `--cap-drop=ALL` (Docker) or `securityContext.capabilities.drop: ["ALL"]` (Kubernetes) as the baseline for every container, then add back only the specific capabilities identified by the diagnostic tracing step -- commonly nothing at all for a typical stateless web service, or just `NET_BIND_SERVICE` for one that binds a privileged port. Treat any capability addition as something that requires the same justification as `privileged: true` -- documented, tied to a specific code path, and re-reviewed whenever that code path changes.

## Pitfalls
Guessing which capabilities to keep based on what "sounds related" to the app's function (e.g. keeping `NET_RAW` for a "networking" service that only ever makes outbound TCP calls, which needs no special capability at all) leads to capability sets that look reduced but still grant meaningfully dangerous access; always verify empirically via the drop-all-and-observe-failures method rather than by category association.

## Verify
After moving to `drop: ALL` plus a minimal add-back list, run the full functional test suite and exercise every code path that previously might have relied on a capability, confirming no `EPERM`/`Operation not permitted` errors appear. Then independently confirm the reduction with `getpcaps <pid>` inside the running container showing exactly the intended minimal set, not the previous default list.
