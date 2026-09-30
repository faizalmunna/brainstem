---
name: overprivileged-pod-security-context
description: A Kubernetes pod runs privileged or with host namespace access it doesn't functionally need, turning any container compromise into a full node compromise.
triggers: ["why does this pod have privileged true set", "pod spec has hostNetwork and hostPID enabled unnecessarily", "security audit flags privileged container in kubernetes"]
permissions: ["READ"]
---

## Symptom
A pod spec is found running with `privileged: true`, `hostNetwork: true`, `hostPID: true`, or `hostIPC: true` set, but the workload is an ordinary application (API server, worker, web app) with no obvious need for host-level access. This typically surfaces in a security audit (kube-bench, Polaris, kube-hunter) or during an incident postmortem where a compromised container was found to have far more reach than the app's actual function required.

## Likely causes
1. **Copy-pasted from a debugging or monitoring workload's manifest** -- privileged mode and host namespace access are legitimately needed by things like node-level monitoring agents or CNI plugins, and a new manifest gets bootstrapped from one of those templates without stripping the flags back out.
2. **A transient debugging need (e.g. needing hostNetwork to test something) was never reverted** after the issue was resolved, because there's no policy gate that would have blocked or flagged it going back to production config.
3. **The workload genuinely needed one specific elevated capability** (e.g. binding to a host port, or accessing `/proc` for some legacy tooling) and the team reached for the broadest privileged flag rather than the narrowest capability that solves it, because it was faster to get working.
4. **No admission control (Pod Security Admission, OPA/Gatekeeper, Kyverno) enforces a restricted baseline**, so nothing in the cluster actually prevents an overprivileged spec from being applied in the first place -- it's a policy gap, not just an authoring mistake.

## Diagnose
1. List the actual security-relevant fields on the pod: `kubectl get pod <pod> -o jsonpath='{.spec.hostNetwork}{.spec.hostPID}{.spec.hostIPC}{"\n"}{.spec.containers[*].securityContext.privileged}'`.
2. For each flag set to true, ask what host-level resource the application code actually touches -- grep the app for direct `/proc/<pid>` access, raw socket usage, or host device access; if none exists, the flag is vestigial.
3. Check whether a Pod Security Standard is enforced on the namespace: `kubectl get ns <namespace> -o jsonpath='{.metadata.labels}'` -- look for `pod-security.kubernetes.io/enforce`; `privileged` or missing means nothing blocks this today.
4. Run `kube-bench` or `polaris audit` against the cluster to get a full inventory of every workload with elevated flags, not just the one under investigation -- this is rarely an isolated case.

## Fix
Replace broad host-namespace/privileged flags with the narrowest mechanism that satisfies the actual requirement: use specific `capabilities.add` entries (e.g. `NET_BIND_SERVICE`) instead of `privileged: true`; use a `hostPort` on the container spec instead of `hostNetwork: true` if only port exposure is needed; avoid `hostPID`/`hostIPC` entirely unless the workload is genuinely a node-level tool (in which case it belongs in a DaemonSet with its own dedicated, audited manifest, not templated into application workloads). Then close the gap that let it happen: enforce Pod Security Admission at `restricted` or `baseline` level on application namespaces, or add an OPA/Gatekeeper or Kyverno policy that rejects `privileged: true` and host namespace flags outside an explicit allowlist of node-agent namespaces.

## Pitfalls
Removing `privileged: true` without first identifying *why* it was set can break the workload in a way that only shows up under specific conditions (e.g. a build step that needs to mount loop devices, or a legacy dependency that shells out to something requiring elevated access) -- always trace the flag to a specific code path before removing it, and test in a staging environment with the same policy enforcement before rolling to production, rather than removing it and hoping.

## Verify
After tightening the security context, confirm the pod still starts and passes its readiness/liveness probes with `kubectl get pod <pod> -w`, then re-run `kube-bench`/`polaris` to confirm the specific finding is cleared. Separately, confirm the admission policy actually blocks a regression by attempting to apply a test manifest with `privileged: true` in that namespace and verifying the API server rejects it with a policy violation error, not just a warning.
