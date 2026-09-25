---
name: writable-root-filesystem-enables-persistence
description: A compromised process inside a container writes a malicious binary or cron-like persistence mechanism to the container's writable root filesystem because nothing prevented filesystem writes outside declared volumes.
triggers: ["attacker dropped a file inside the container filesystem", "should our containers run with a read-only root filesystem", "malware persisted inside a running container after compromise"]
permissions: ["READ"]
---

## Symptom
During an incident review or a security hardening pass, it's discovered that a compromised container process was able to write arbitrary files anywhere in the container's filesystem -- a webshell dropped next to application code, a modified binary in `/usr/bin`, a cron-like persistence script -- because the container's root filesystem is fully writable by default. In many cases the change is only caught because the container was eventually restarted and monitoring flagged filesystem drift, or not caught at all until further lateral movement occurred.

## Likely causes
1. **No `readOnlyRootFilesystem` (Kubernetes) or `--read-only` (Docker) flag is set**, which is the default for most container runtimes -- the root filesystem is writable everywhere unless explicitly locked down.
2. **The application actually does need to write somewhere (logs, temp files, cache, uploads) and the team never separated "needs a writable path" from "needs a writable entire filesystem"** -- so instead of mounting a specific writable volume/emptyDir for those paths, the whole root stays writable to avoid dealing with the distinction.
3. **A base image or framework writes to unexpected locations at runtime** (e.g. writing compiled bytecode cache next to source, or a package manager lockfile touch) that wasn't accounted for when read-only was first attempted, causing an earlier attempt at read-only mode to be abandoned rather than fixed with a targeted writable mount.
4. **No file-integrity monitoring or runtime security tool** (Falco, Sysdig, auditd-based) is deployed to detect unexpected writes to sensitive paths even when the filesystem is technically writable, so there's no independent detection layer as a backstop.

## Diagnose
1. Check the current setting: for Docker, `docker inspect <container> --format '{{.HostConfig.ReadonlyRootfs}}'`; for Kubernetes, `kubectl get pod <pod> -o jsonpath='{.spec.containers[0].securityContext.readOnlyRootFilesystem}'` -- `false`/empty confirms the gap.
2. If read-only was attempted before and reverted, check container logs and crash history around that time for `Read-only file system` errors to identify exactly which paths the application needs writable.
3. Trace what the application actually writes at runtime using `strace -f -e trace=open,openat,write <pid>` inside a running instance (or `docker diff <container>` after normal operation) to get a concrete list of write targets rather than guessing.
4. If investigating a suspected compromise, run `docker diff <container>` (or compare a filesystem hash snapshot against the original image layers) to enumerate every file added/changed since container start -- this is the direct evidence of unauthorized persistence.

## Fix
Set the root filesystem to read-only (`readOnlyRootFilesystem: true` in the pod securityContext, or `--read-only` in plain Docker) and explicitly mount writable volumes only for the specific paths the application legitimately needs -- typically an `emptyDir` for `/tmp`, a dedicated volume for application logs if not shipped to stdout, and any explicit cache/upload directories identified during diagnosis. This turns "everything is writable" into "only these three known, monitored paths are writable," which both prevents arbitrary persistence and makes any write to those specific paths a much higher-signal thing to monitor.

## Pitfalls
Flipping on read-only mode without first running the strace/diff audit step causes a wave of hard-to-debug crashes (package managers trying to write lockfiles, logging libraries trying to create files next to the binary, language runtimes writing bytecode cache) that look unrelated to the security change -- teams sometimes respond by reverting to writable entirely rather than mounting the two or three specific paths that were actually needed, throwing away the hardening.

## Verify
After enabling read-only mode with the targeted writable mounts, run the application through its normal functional test suite and confirm no `Read-only file system` errors appear in logs. Then confirm the hardening actually holds: attempt a write to a path outside the declared writable mounts from inside a running container (`docker exec <container> touch /usr/bin/test`) and confirm it's rejected with a permission/read-only error.
