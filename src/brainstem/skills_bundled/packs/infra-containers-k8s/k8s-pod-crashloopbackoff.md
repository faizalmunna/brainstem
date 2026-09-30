---
name: k8s-pod-crashloopbackoff
description: Systematically diagnose a Kubernetes pod stuck in CrashLoopBackOff instead of guessing at the fix from the pod name alone.
triggers: ["crashloopbackoff", "pod keeps restarting", "pod crash loop", "kubectl pod restarting", "container keeps crashing kubernetes"]
permissions: ["READ"]
---

## Symptom
`kubectl get pods` shows a pod in `CrashLoopBackOff` status, with its
restart count climbing -- the container starts, exits (crashes or is
killed), and Kubernetes keeps restarting it with increasing backoff delay.

## Likely causes
1. **The application itself crashes on startup** -- a missing environment
   variable/config, a failed dependency connection (database not yet
   reachable), or an unhandled startup exception.
2. **The container's main process exits immediately** because it was
   configured to run something that isn't a long-running process (a
   one-shot command instead of a server), or the entrypoint/command is
   misconfigured.
3. **Liveness probe killing an otherwise-healthy container** -- the probe
   is checking too aggressively (too short a timeout/initial delay) for
   an app that takes longer to become ready, so Kubernetes kills a
   container that would have started fine given more time.
4. **OOMKilled** -- the container exceeds its memory limit and the kernel
   OOM-killer terminates it, which shows up as a crash loop but has a
   distinct, checkable root cause (memory limit vs. actual usage).
5. **A missing or misconfigured dependency the app requires at startup**
   (a ConfigMap/Secret not mounted, a required environment variable
   unset), causing the app's own startup validation to fail fast.

## Diagnose
- `kubectl describe pod <name>` first: check the `Last State`/`Reason`
  field specifically -- `OOMKilled` points directly to cause 4, distinct
  from a generic non-zero exit code.
- `kubectl logs <pod> --previous` to see the *previous* (crashed)
  container's output, since the current instance may not have logged
  anything yet -- this is the single most useful command for causes 1, 2,
  and 5.
- Check the pod spec's `livenessProbe` configuration (`initialDelaySeconds`,
  `timeoutSeconds`, `failureThreshold`) against how long the app actually
  takes to become ready, to rule out/in cause 3.
- Check `resources.limits.memory` against actual observed memory usage
  (via `kubectl top pod` while it's briefly running, or metrics/APM data)
  to rule out/in cause 4.

## Fix
- For an application startup crash, fix the underlying issue (missing
  config, unreachable dependency) directly -- the crash loop is a
  symptom, `kubectl logs --previous` names the actual error.
- For a misconfigured entrypoint, correct the container's `command`/`args`
  (or the image's own entrypoint) to run the actual long-running server
  process, not a one-shot script.
- For an over-aggressive liveness probe, increase `initialDelaySeconds`
  to comfortably exceed real startup time, and consider adding a separate
  `startupProbe` (which suppresses liveness checks until startup
  succeeds) for apps with variable/slow cold-start time, rather than just
  loosening the liveness probe's steady-state sensitivity.
- For OOMKilled, either raise the memory limit to match real usage (after
  confirming the usage itself isn't a leak) or fix an actual memory leak/
  inefficiency in the application -- raising the limit without checking
  which it is just delays the same failure at a higher memory ceiling.
- For missing dependencies, ensure required ConfigMaps/Secrets are
  created and mounted before the pod starts, and add an init container
  or startup retry/backoff in the app itself if it needs to wait for a
  dependency (e.g. a database) to become ready.

## Pitfalls
- Increasing `failureThreshold`/probe timeouts broadly to "stop the
  crash loop" can mask a genuinely hung/broken application by simply
  waiting longer before declaring it unhealthy, delaying detection of a
  real problem rather than fixing it.
- Raising memory limits reflexively on every OOMKilled pod, without
  checking whether usage is a genuine requirement or a leak, hides
  leaks until they eventually exceed whatever the new limit is too.

## Verify
After the fix, watch `kubectl get pods -w` through several of the
previous crash-loop's typical restart interval and confirm the pod
reaches and stays in `Running`/`Ready` status, and check
`kubectl describe pod` shows no new restarts accumulating.
