---
name: vpc-service-controls-blocks-legitimate-api-call
description: A legitimate API call to a GCP service is blocked with an access-denied error because VPC Service Controls perimeter rules don't explicitly allow it, despite correct IAM permissions.
triggers: ["vpc service controls blocking request", "gcp perimeter violation despite correct iam", "vpc-sc denies request with correct permissions", "service perimeter blocks api call"]
permissions: ["READ"]
---

## Symptom

A request to a GCP API fails with an access-denied error referencing
VPC Service Controls (a "Request is prohibited by organization's policy"
or similar perimeter violation message), even though the calling
identity clearly has the correct IAM roles/permissions for the operation
being attempted -- the failure is happening at a different security layer
than IAM.

## Likely causes

- **The calling identity or resource is inside a VPC Service Controls
  perimeter, and the target API/resource is outside it** (or vice versa),
  and no explicit egress/ingress rule permits that specific
  cross-perimeter access, regardless of IAM permissions -- VPC-SC and
  IAM are separate, independently enforced layers.
- **A newly added GCP service or API endpoint isn't included in the
  perimeter's list of protected/restricted services**, or conversely IS
  now restricted after an update to the perimeter configuration, and
  nobody updated the perimeter's access levels to account for the
  application's actual usage of that service.
- **The request originates from a context VPC-SC doesn't recognize as
  "inside" the perimeter** (a local developer machine, a CI runner
  outside the configured network) even though it holds valid credentials,
  since VPC-SC evaluates network/context origin in addition to identity.
- **An access level (a set of allowed IP ranges, device policies, or
  identity conditions) that should grant the exception is misconfigured
  or doesn't match the actual calling context's real attributes**.

## Diagnose

1. Read the exact VPC-SC violation error/audit log entry (Cloud Audit
   Logs record perimeter violations with specific detail about which
   perimeter, which service, and which access level check failed) rather
   than assuming it's a generic permission issue.
2. Check the perimeter's configuration for which projects/resources are
   inside it, and where the calling identity/resource and target
   API/resource actually sit relative to that boundary.
3. Check the perimeter's ingress/egress rules and access levels for
   whether an explicit rule exists permitting this specific combination
   of caller context and target service.
4. If the caller is external to GCP's network context (a local machine,
   an external CI runner), check whether an access level based on
   identity plus some other condition (not just network origin) is
   configured to allow it.

## Fix

Add an explicit ingress/egress rule or access level to the VPC Service
Controls perimeter configuration that permits the specific legitimate
access pattern (the specific calling identity, service, and/or network
context involved), rather than assuming IAM permissions are sufficient
on their own. For access needed from outside the perimeter's network
context (external CI, developer machines), configure an access level
based on verified identity/device conditions appropriate to the
organization's security requirements, rather than disabling VPC-SC
enforcement broadly.

## Pitfalls

Don't respond to a VPC-SC violation by removing the resource/project
from the perimeter entirely, or by making the perimeter's rules overly
permissive, as a quick fix -- that defeats the purpose VPC-SC was
deployed for (typically preventing data exfiltration across a security
boundary) and should go through the same review process that established
the perimeter in the first place, since it's a security control, not
just an operational obstacle.

## Verify

After adding the specific, scoped access level or rule, retry the
original legitimate request and confirm it now succeeds, and confirm
(by attempting a different, genuinely out-of-policy request) that the
perimeter still correctly blocks access patterns it's meant to prevent --
proving the fix was scoped narrowly rather than broadly weakening the
perimeter.
