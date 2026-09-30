---
name: model-version-rollout-breaks-client-compatibility
description: Deploying a new model version breaks calling applications because its output shape, label set, or value ranges silently differ from what client code was written to expect.
triggers: ["new model version broke client", "model output format changed unexpectedly", "model deployment broke downstream", "inference output schema changed silently"]
permissions: ["READ"]
---

## Symptom

Deploying a new version of a served model (retrained, fine-tuned, or
architecturally updated) causes calling applications to break or behave
incorrectly -- not because the model's accuracy changed, but because its
output format, label set, value range, or schema differs from the
previous version in a way client code wasn't written to handle.

## Likely causes

- **The new model version was trained/exported with a different output
  schema** (a different number of classes, reordered label indices, a
  different confidence score scale) than the previous version, and no
  compatibility check existed to catch this before deployment.
- **Model deployment and client code are versioned/deployed
  independently**, so there's no coordinated release process ensuring
  client code is updated in lockstep with a breaking model change, or
  that a breaking change is avoided in favor of a backward-compatible
  one.
- **A retraining pipeline changed feature preprocessing (a different
  normalization, a different encoding for categorical inputs) without
  the serving/client layer being updated to match**, causing correct-
  looking but actually mismatched inputs to reach the new model.
- **No contract/schema validation exists between model output and client
  expectations**, so a breaking change is only caught when it causes a
  visible failure or, worse, silently wrong behavior downstream.

## Diagnose

1. Diff the old and new model version's actual output schema (run both
   against the same test input and compare output structure, value
   ranges, and label mappings) to identify exactly what changed.
2. Check the model training/export pipeline's configuration history for
   what changed between the two versions that would explain the output
   difference.
3. Check whether any schema/contract validation step exists in the
   deployment pipeline that should have caught this before the new
   version went live.
4. Identify all client applications currently consuming this model's
   output and assess which ones are actually broken versus merely at
   risk.

## Fix

Establish an explicit output contract/schema for the model (documented
label mappings, value ranges, output structure) and validate any new
model version against that contract before deployment, failing the
deployment if the contract is violated unless the change is
deliberately versioned as a breaking change with coordinated client
updates. For genuinely necessary breaking changes, use a new model
version/endpoint (versioned API path) rather than mutating the existing
one in place, so existing clients continue working against the old
version until they're explicitly migrated. Add automated comparison
testing between model versions as part of the deployment pipeline,
specifically checking output schema/format compatibility, not just
accuracy metrics.

## Pitfalls

Don't rely solely on accuracy/performance metrics to gate model
deployment -- a new version can have excellent accuracy while still
breaking every downstream consumer due to a schema change; schema/
contract compatibility is a separate check that needs its own explicit
gate. Also don't assume "the model improved" is sufficient justification
to skip compatibility validation -- coordinate the breaking change
properly even when the underlying model quality genuinely improved.

## Verify

Run the new model version's output through the established schema
validation and confirm it passes (or is deliberately flagged as an
intentional breaking change requiring coordinated rollout). Confirm all
identified client applications work correctly against the new version
before it fully replaces the old one in production traffic.
