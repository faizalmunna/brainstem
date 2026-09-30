---
name: execution-role-overpermissioned-blast-radius
description: A function's execution role grants far more permissions than its actual code path uses, widening the blast radius if the function is ever compromised.
triggers: ["lambda execution role too permissive", "function has more iam permissions than it needs", "serverless least privilege audit", "lambda role wildcard permissions"]
permissions: ["READ"]
---

## Symptom
A security review, IAM Access Analyzer report, or post-incident audit
turns up a function whose execution role can read/write resources (other
tables, buckets, secrets, entire service actions with wildcards) that
nothing in the function's actual code ever touches. Nobody added those
permissions maliciously -- they accumulated because it was faster to
attach a broad managed policy or copy a role from a similar function than
to scope one precisely, and the gap between "what the role allows" and
"what the code does" was never revisited.

## Likely causes
1. **The role was created by attaching a broad AWS-managed policy** (e.g.,
   `AmazonS3FullAccess`, `AmazonDynamoDBFullAccess`) to get something
   working quickly during initial development, and the "make it work
   first, scope it down later" step never happened once the function
   shipped.
2. **The role was copied from another function** ("this one does
   something similar, just reuse its role") without checking whether the
   copied permissions actually match the new function's code path, so
   permissions accumulate across the fleet by inheritance rather than by
   deliberate grant.
3. **Permissions were added reactively to fix an `AccessDenied` error**
   during debugging by widening a resource ARN to `*` or an action to a
   service-level wildcard (`dynamodb:*`) to "just make the error go away,"
   without narrowing it back down once the actual missing permission was
   identified.
4. **The function's code path changed over time** (a feature that used to
   write to a second table was removed) but the IAM policy was never
   updated to match, so the role reflects the function's history rather
   than its current behavior.
5. **The infrastructure-as-code module used to provision the function has
   a "one size fits all" role baked in for convenience** across many
   functions in the same stack, trading per-function precision for
   less Terraform/CDK boilerplate.

## Diagnose
- Enable/review AWS IAM Access Analyzer's "unused access" findings (or the
  equivalent least-privilege advisor for the platform) for the function's
  role -- it flags granted actions and resources that haven't actually
  been used in the lookback window, which is direct evidence of excess
  scope.
- Cross-reference the role's policy document against a grep of the
  function's actual source code for every SDK call it makes (every
  `dynamodb.`, `s3.`, `secretsmanager.` client call) -- build the real
  "what this code does" list by hand and diff it against "what the policy
  allows."
- Check CloudTrail for the actual API calls made using this role's
  credentials over a representative time window (weeks, not hours, to
  catch infrequent code paths) -- calls in the policy that never appear
  in CloudTrail are candidates for removal.
- Look specifically for `"Resource": "*"` or service-level action
  wildcards (`"Action": "s3:*"`) in the policy document -- these are the
  highest-value targets to scope down to specific ARNs and specific
  actions.
- Check whether the role is shared/reused across multiple functions with
  different actual responsibilities -- a shared role is a strong signal
  that its permissions are a superset of what any single function needs.

## Fix
Derive the role's policy from the function's actual code path, not from a
convenient managed policy or a copied role -- list every specific action
the code calls and every specific resource ARN it touches, and write a
scoped inline or customer-managed policy that grants exactly that.
Replace wildcard resources with specific ARNs (including the table/bucket
name and, where supported, condition keys narrowing by prefix or tag) and
replace service-level action wildcards with the specific action list the
code uses. When permissions were widened reactively to fix an
`AccessDenied` during debugging, treat that as a temporary diagnostic
step, not a resolution -- follow up by identifying the exact missing
action/resource and narrowing back down before merging. For roles shared
across similar functions, split them so each function's role reflects
only its own code path, even if that means more roles to manage --
Infrastructure-as-code modules can template the scoping logic without
sharing the actual role.

## Pitfalls
Over-scoping in the other direction -- writing a policy so narrow it
breaks on the next minor code change (a new field read from a different
table) -- creates a cycle of emergency wildcard grants to unblock a
deploy, which is exactly how over-permissioning happens in the first
place; the fix is a deliberate review step before merging IAM changes,
not oscillating between too-broad and too-narrow under time pressure.
Also, scoping the policy correctly but leaving the role's *trust policy*
overly permissive (allowing it to be assumed from contexts beyond the
function's own service) leaves a separate privilege-escalation path that
a resource-permission audit alone won't catch.

## Verify
After deploying the scoped-down policy, run the function through its full
set of code paths (including error/edge-case branches, not just the happy
path) in a non-production environment and confirm zero `AccessDenied`
errors appear in logs; then re-run the Access Analyzer unused-access check
after a representative production traffic window and confirm no granted
action/resource remains flagged as unused.
