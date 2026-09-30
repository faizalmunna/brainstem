---
name: container-process-running-as-root
description: A container's main process runs as root by default so any code-execution vulnerability inside it gains root privileges within the container immediately.
triggers: ["docker exec shows uid 0 inside the container", "why is our app running as root in the container", "security scan flags container running as root user"]
permissions: ["READ"]
---

## Symptom
`docker exec -it <container> whoami` or `id` returns `root`/`uid=0` for the application process, and a security scanner or audit tool (Trivy config scan, kube-bench, Docker Bench) flags "container running as root" as a finding. The application itself works fine -- this only becomes visible when someone deliberately checks the running user or when it's flagged in an audit, or catastrophically, after an actual compromise where the attacker's shell is also root.

## Likely causes
1. **The Dockerfile never declares a `USER` instruction**, so the container inherits root from the base image by default -- most base images (including many "slim" ones) default to root unless a downstream layer explicitly drops privileges.
2. **A non-root user was added but a later `RUN` step needs root** (installing packages, writing to a system path) **and the `USER` switch-back was forgotten** after that step, leaving the final image running as root even though a non-root user exists in `/etc/passwd`.
3. **The application needs to bind to a privileged port (<1024)** like 80 or 443, and the team runs as root as the "easy" fix instead of using a higher port with a reverse proxy/ingress remapping it, or granting `CAP_NET_BIND_SERVICE` to a non-root user.
4. **Orchestrator-level `runAsNonRoot`/`securityContext` enforcement is missing**, so even if a non-root user is theoretically available, nothing in the deployment config actually requires it, and a future image rebuild can silently regress back to root.

## Diagnose
1. Inspect the built image directly without running it: `docker inspect --format '{{.Config.User}}' myimage:tag` -- an empty string means root by default.
2. If the Dockerfile has a `USER` line, check its position relative to other `RUN`/`COPY` instructions -- confirm nothing after it switches back to root or omits `USER` on a later stage in a multi-stage build (each stage resets to root unless it also declares `USER`).
3. Run the container and check live: `docker exec <container> id` -- confirm both the primary UID and any supplementary groups are non-zero.
4. For Kubernetes, check the pod's effective security context: `kubectl get pod <pod> -o jsonpath='{.spec.securityContext}{.spec.containers[0].securityContext}'` -- absence of `runAsNonRoot: true` or `runAsUser` means the cluster isn't enforcing anything beyond whatever the image itself does.

## Fix
Create a dedicated non-root user in the Dockerfile and switch to it as the last step before `CMD`/`ENTRYPOINT`, ensuring the user owns any directories the app needs to write to (chown them before the `USER` switch, since the switch happens as the final privilege). For privileged-port binding, avoid running as root entirely -- either have the app listen on a high port (e.g. 8080) with the orchestrator's Service/Ingress mapping port 80 externally, or grant the specific `CAP_NET_BIND_SERVICE` capability to the non-root user instead of full root. In multi-stage builds, repeat the `USER` declaration in the final stage since it doesn't carry over from earlier stages. At the orchestrator level, enforce this with `securityContext.runAsNonRoot: true` and a specific `runAsUser` so a future image regression is rejected at deploy time rather than silently accepted.

## Pitfalls
Adding `USER 1000` without creating and naming that UID, and without ensuring the application's writable directories (logs, cache, tmp, upload dirs) are chowned to that UID beforehand, causes the container to crash-loop on permission-denied errors -- teams sometimes "fix" this by reverting to root rather than fixing the ownership, which defeats the purpose entirely.

## Verify
Rebuild the image and run `docker run --rm myimage:tag id` -- confirm it reports a non-zero UID with no error. Then exercise the application's actual write paths (log rotation, temp file creation, cache writes) under the non-root user to confirm no permission errors, and in Kubernetes, confirm `kubectl get pod -o yaml` shows the enforced `runAsNonRoot: true` and that a manually-crafted pod spec attempting to run as root against that same PodSecurity/OPA policy is rejected.
