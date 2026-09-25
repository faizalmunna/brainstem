---
name: k8s-secrets-configmap-mistakes
description: Diagnose Kubernetes Secret/ConfigMap mistakes -- stale mounted config after update, secrets visible in plaintext, or a pod reading the wrong environment's values.
triggers: ["configmap not updating", "secret not reloaded", "kubernetes secret plaintext", "config change not picked up pod", "wrong environment config kubernetes"]
permissions: ["READ", "SECRET"]
---

## Symptom
One of: updating a `ConfigMap`/`Secret` doesn't take effect in already-
running pods; a Secret's value is visible in plaintext somewhere it
shouldn't be (logs, `kubectl describe`, version control); or a pod is
unexpectedly using a different environment's configuration values than
intended.

## Likely causes
1. **ConfigMap/Secret mounted as a volume, but the application doesn't
   reload it** -- Kubernetes does update the mounted file's content
   automatically (with a propagation delay), but many applications read
   config once at startup and never watch the file for changes, so the
   *pod's file* updates while the *running process's in-memory config*
   doesn't.
2. **ConfigMap/Secret injected as environment variables**, which are
   fundamentally static at container start -- an env-var-based config
   update requires a pod restart no matter what, since environment
   variables can't be changed for a running process from outside it.
3. **Secret committed to version control or logged in plaintext** --
   passed via a plain YAML manifest checked into git, or an application
   logging its full configuration (including secret values) at startup
   for debugging.
4. **Wrong ConfigMap/Secret referenced** due to a naming collision or
   copy-pasted manifest across environments (a `staging` deployment
   accidentally referencing the `production` Secret name, or vice versa)
   without a namespace or naming convention that makes this obvious/
   enforced.

## Diagnose
- Check how config reaches the application: volume-mounted file vs.
  environment variable -- this determines whether an update can ever take
  effect without a restart at all.
- For volume-mounted config, check whether the application actually
  watches the file for changes (many frameworks need an explicit
  file-watcher or a signal-based reload) versus reading it once at
  startup.
- Grep application logs for evidence of secret values being logged
  (common when a "log the full config on startup" debug statement wasn't
  scrubbed).
- Check the deployment manifest's Secret/ConfigMap references against the
  actual intended environment, and check version control history for
  any Secret manifest that was committed with real values rather than
  a reference/placeholder.

## Fix
- For config that needs to be dynamically reloadable, mount it as a
  volume (not environment variables) and either use a library/sidecar
  that watches the file for changes and triggers a reload, or explicitly
  restart/roll the deployment after a ConfigMap/Secret update if live
  reload isn't implemented -- both are legitimate, but be deliberate
  about which one the application actually supports.
- For anything using environment-variable injection, treat "requires pod
  restart to pick up changes" as expected behavior, and roll the
  deployment (e.g. `kubectl rollout restart`) as the actual mechanism for
  applying a config/secret change, rather than expecting it to apply
  live.
- Never commit real Secret values to version control -- use a secrets
  manager integration (external-secrets operator, sealed-secrets, cloud
  provider secret manager) that generates the Kubernetes Secret from an
  external, access-controlled source, keeping only a reference (not the
  value) in version control.
- Remove/scrub any startup logging that dumps full configuration
  including secret fields; log configuration with secret values
  explicitly redacted.
- Adopt a clear, enforced naming/namespace convention that makes
  cross-environment Secret/ConfigMap misreferences visually obvious in
  the manifest (e.g. namespace-per-environment rather than relying on
  name suffixes alone).

## Pitfalls
- Restarting pods to force a config reload without confirming the new
  ConfigMap/Secret content is actually correct first can roll out a
  broken config faster and to more replicas than a gradual/canary
  approach would have caught.
- Removing a secret from version control after the fact doesn't remove it
  from git history -- a leaked secret needs to be rotated (a new value
  issued and the old one invalidated), not just deleted from the current
  file.

## Verify
Update the ConfigMap/Secret, trigger whatever reload mechanism is
actually in place (file-watch or rollout restart), and confirm via the
application's actual behavior (not just the mounted file's content) that
the new value is in effect -- and separately, confirm no secret value
appears in `kubectl describe`, application logs, or version control
history going forward.
