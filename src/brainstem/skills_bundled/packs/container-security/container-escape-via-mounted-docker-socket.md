---
name: container-escape-via-mounted-docker-socket
description: A container has the host's Docker socket mounted inside it for convenience, giving any process in that container root-equivalent control over the entire host.
triggers: ["we mounted var run docker sock into the container", "ci runner container has docker.sock bind mounted", "is mounting the docker socket into a container a security risk"]
permissions: ["READ"]
---

## Symptom
A container -- commonly a CI/CD runner, a monitoring agent, or a "docker-in-docker" build helper -- is configured with `-v /var/run/docker.sock:/var/run/docker.sock` (or the Kubernetes hostPath equivalent), so that it can launch sibling containers on the host. This is often set up specifically to solve a legitimate build problem, but it's rarely recognized at setup time that anything with write access to that socket has effective root access to the entire host, not just "the ability to run more containers."

## Likely causes
1. **A CI pipeline needs to build and run Docker images as part of its job**, and the fastest way found online to enable "Docker-in-Docker" was mounting the host socket rather than using a properly isolated DinD sidecar or rootless build tool.
2. **A monitoring/observability agent needs container-level metrics** (container names, resource stats) and was given the Docker socket as the broadest way to get that information, when a narrower, read-only metrics API or the container runtime's dedicated stats socket would have sufficed.
3. **The risk is underestimated because the mount is inside "just a container," not directly on the host** -- the mental model "it's containerized, so it's sandboxed" doesn't hold here, because socket access lets a process trivially launch a new container with `-v /:/host` and chroot into the full host filesystem, fully escaping any container boundary.
4. **No policy or admission control blocks `hostPath` mounts of the Docker/containerd socket**, so this pattern can be introduced by any team without review, and often is, because it "just works" for the immediate problem.

## Diagnose
1. Search all deployment manifests and Dockerfiles/compose files for the socket path: grep for `docker.sock` or `containerd.sock` across `docker-compose.yml`, Kubernetes manifests, and Helm values -- any hostPath or bind mount referencing it is a hit.
2. For any match, confirm the mount is writable, not read-only (`docker inspect <container> --format '{{.Mounts}}'`) -- a genuinely read-only mount is still risky but a writable one is unambiguous root-equivalent access.
3. Demonstrate the actual blast radius in a non-production environment: from inside the container with socket access, run `docker -H unix:///var/run/docker.sock run -v /:/host --rm -it alpine chroot /host sh` and confirm it drops into a full host shell -- this concretely proves the escape path to stakeholders who may see it as "just a build convenience."
4. Check whether the workload with socket access also runs with reduced privileges otherwise (non-root user, dropped capabilities) -- note that none of that matters for this specific risk, since socket access alone bypasses all of it.

## Fix
Replace host-socket mounting with a properly isolated build mechanism: for CI, use rootless build tools that don't require a daemon at all (Buildah, Kaniko, `docker buildx` with a dedicated isolated builder), or a Docker-in-Docker sidecar container with its own isolated daemon rather than sharing the host's. For monitoring/metrics use cases, use the container runtime's dedicated read-only metrics endpoint or the Kubernetes API's resource metrics rather than direct socket access. If socket access is truly unavoidable for a specific tool, isolate that workload onto dedicated nodes with no other sensitive workloads scheduled alongside it, since anything on the same node with socket-holding pods should be treated as within that pod's trust boundary.

## Pitfalls
Believing that mounting the socket read-only (`:ro`) meaningfully mitigates the risk is a common mistake -- the Docker API exposed over that socket is inherently capable of container creation and host filesystem access via volume mounts regardless of the mount flag on the socket file itself; `:ro` only affects whether the *socket file* can be modified, not what the Docker daemon will do with commands sent over it.

## Verify
After migrating away from the shared host socket, confirm the build/monitoring workload still functions using the new isolated mechanism (build completes successfully, metrics still populate). Then confirm the escape path is actually closed: attempt the same `docker -H unix:///var/run/docker.sock` command from inside the affected container and confirm the socket is no longer present/accessible (connection refused or no such file).
