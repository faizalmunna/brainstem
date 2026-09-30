---
name: aks-image-pull-acr-managed-identity-denied
description: An AKS pod fails to start with ImagePullBackOff because the cluster's managed identity lacks the AcrPull role or was never attached to the registry.
triggers: ["aks imagepullbackoff acr", "aks pod cannot pull image from container registry", "AKS unauthorized to access repository", "az aks update attach-acr not working"]
permissions: ["READ"]
---

## Symptom
Pods scheduled on an AKS cluster sit in `ImagePullBackOff` or
`ErrImagePull` when pulling from Azure Container Registry (ACR), even
though the same image can be pulled successfully with `docker pull` or
`az acr login` using a user's own credentials, and the image definitely
exists in the registry at the tag referenced.

## Likely causes
1. **The AKS cluster's kubelet identity was never granted `AcrPull` on the
   target registry** -- `az aks create`/`update --attach-acr` is the
   supported path to wire this up, but if the cluster was created without
   it, or the registry was created/renamed afterward, the role assignment
   simply doesn't exist and every pull is an authorization failure, not a
   network or image-name problem.
2. **The cluster is using the wrong identity for the pull path** -- AKS
   has both a cluster (control plane) managed identity and a separate
   kubelet identity that actually authenticates to ACR for image pulls in
   newer AKS versions; a role assignment made against the wrong one (e.g.,
   the control-plane identity instead of the kubelet identity) looks
   correct in the portal but doesn't authorize the actual pull path.
3. **The role assignment exists but hasn't propagated yet**, since Azure
   RBAC role assignments can take several minutes to become effective
   cluster-wide, so pods scheduled immediately after running
   `--attach-acr` can fail while an identical pull minutes later succeeds.
4. **A private ACR with network restrictions (private endpoint or
   firewall rules) blocks the AKS cluster's outbound path**, so even with
   correct RBAC, the pull fails at the network layer with an error that
   can look similar to an auth failure in kubectl's summarized event
   message -- this is a distinct cause from missing `AcrPull` and requires
   checking ACR's network rules, not IAM.
5. **The image reference itself doesn't match what's actually in the
   registry** (wrong ACR login server hostname, e.g., a leftover reference
   to a different registry after a rename/migration, or a tag that was
   deleted by a retention policy) -- worth ruling out before assuming it's
   purely an identity problem, since the pod event message for a missing
   image and a denied pull can look similar at a glance.

## Diagnose
- Run `kubectl describe pod <pod>` and read the full Events section --
  differentiate `unauthorized: authentication required` / `403` (identity
  problem) from `manifest unknown` / `not found` (wrong image reference)
  from a generic network timeout (connectivity/firewall problem); these
  point to different fixes.
- Run `az aks show -g <rg> -n <cluster> --query identityProfile` to
  identify the actual kubelet identity object ID, then
  `az role assignment list --assignee <kubelet-identity-object-id> --scope
  <acr-resource-id>` to confirm `AcrPull` is actually assigned to that
  specific identity, not the cluster's control-plane identity.
- Check `az acr show --name <registry> --query
  networkRuleBypassOptions,publicNetworkAccess` and any configured private
  endpoints/firewall IP rules to rule out network-layer blocking
  independent of RBAC.
- From a debug pod or node shell inside the cluster, attempt
  `curl -v https://<registry>.azurecr.io/v2/` to isolate whether the
  cluster can reach the registry endpoint at all before worrying about
  auth.
- Check `az acr repository show-tags --name <registry> --repository
  <repo>` to confirm the exact tag referenced in the pod spec still exists
  and wasn't purged by a retention policy.

## Fix
Use `az aks update --name <cluster> --resource-group <rg> --attach-acr
<registry>` (or the equivalent Terraform/Bicep `role_assignment` against
the correct kubelet identity) as the supported, idempotent way to wire up
pull access -- it grants `AcrPull` to the correct identity for the
cluster's actual configuration (managed identity or, on older clusters,
service principal) rather than hand-rolling a role assignment against a
guessed identity. If the registry has network restrictions, ensure the
AKS cluster's outbound path (via its subnet, NAT gateway, or private
endpoint if using a private AKS/ACR pairing) is explicitly allowed,
treating network access and RBAC as two independent gates that both must
pass. After attaching, wait for propagation and re-test rather than
immediately concluding the attach failed.

## Pitfalls
Falling back to an imagePullSecret with long-lived ACR admin credentials
"to just get it working" reintroduces a static secret that has to be
rotated and stored securely, undoing the reason to use managed identity
in the first place -- treat that as a temporary diagnostic bypass, not the
fix, and remove it once `--attach-acr` is confirmed working. Also, don't
assume `--attach-acr` failing silently means it didn't run; check the
actual role assignment afterward, since a caller lacking
`Microsoft.Authorization/roleAssignments/write` on the ACR's scope can
cause the command to partially succeed on the AKS side while the role
assignment itself never gets created.

## Verify
Delete the failing pod (or scale the deployment) to force a fresh pull
attempt and confirm with `kubectl get pods -w` that it reaches `Running`.
Re-run `az role assignment list` against the kubelet identity and the
registry scope to confirm `AcrPull` is present. Confirm no
`imagePullSecrets` were left in the pod spec as a leftover workaround if
the intent was to rely solely on the managed identity path.
