---
name: unexpected-resource-replacement-forced-attribute
description: A terraform plan shows a resource will be destroyed and recreated even though only a seemingly minor, unrelated-looking attribute changed.
triggers: ["terraform plan wants to destroy and recreate", "force new resource terraform", "terraform plan -/+ resource", "why is terraform recreating this resource", "terraform replace unexpected"]
permissions: ["READ"]
---

## Symptom
`terraform plan` output shows a resource marked `-/+` (destroy and
recreate) instead of the expected `~` (in-place update), even though the
config change looks small and unrelated to anything that should require
replacement -- for example changing a tag, an availability zone, or a
name prefix, and suddenly the entire resource (and its dependents) is
slated for destruction and recreation.

## Likely causes
1. **The changed attribute is marked `ForceNew` in the provider schema**,
   meaning the underlying cloud API has no update operation for that
   field at all -- the provider's only way to apply the change is to
   delete and recreate the resource, regardless of how trivial the value
   change looks from the config's perspective.
2. **A different attribute changed as a side effect**, not the one the
   author thinks changed -- e.g. changing a `name` that's used to derive
   another computed identifier, or a module input that flows into an
   attribute the plan output doesn't show clearly at first glance.
3. **An upstream value the resource depends on is itself changing**,
   propagating a forced replacement downstream through the dependency
   graph (e.g. a subnet's CIDR changing forces the subnet to be replaced,
   which in turn forces every resource that references its ID to be
   replaced too).
4. **A provider version upgrade changed which attributes are `ForceNew`**
   for that resource type, so identical configuration that previously
   produced an in-place update now produces a replacement after `terraform
   init -upgrade`.

## Diagnose
- Run `terraform plan` and read the full reason line -- modern Terraform
  prints `# forces replacement` directly next to the specific attribute
  causing it; do not assume it's the attribute you just edited without
  confirming against this line.
- Run `terraform plan -out=tfplan` then `terraform show -json tfplan` and
  inspect the `resource_changes[].change.actions` and
  `...replace_paths` fields to get the exact attribute path Terraform
  used to decide on replacement, especially when multiple attributes
  changed at once.
- Check the provider's resource documentation (or the provider source's
  schema for that resource) for which arguments are documented as
  "Changing this forces a new resource" -- this is often stated per
  argument and is the authoritative answer, not guesswork from the plan
  diff alone.
- If a provider upgrade preceded this, diff the provider's CHANGELOG
  between the old and new pinned versions for the resource in question,
  searching for "ForceNew," "now requires replacement," or similar
  schema-change language.

## Fix
Once the specific `ForceNew` attribute is identified, choose deliberately
between accepting the replacement (if it's safe -- stateless resources,
resources with no meaningful downtime cost) or avoiding it: for resources
where recreation is destructive (e.g. a database, a resource holding
persistent identity other systems reference), use `lifecycle {
create_before_destroy = true }` to reduce downtime by creating the
replacement before destroying the original, or restructure the config to
avoid touching the `ForceNew` field entirely (e.g. move a value that
doesn't need to force replacement out of the attribute that triggers it,
if the provider offers a separate non-`ForceNew` argument for a related
purpose). When the replacement cascades from an upstream resource, decide
at the *root* of the cascade, not at each downstream resource
individually -- fixing the leaf symptom while the root still forces
replacement just moves the problem.

## Pitfalls
- Adding `create_before_destroy = true` blindly to "fix" a scary-looking
  plan without checking for naming collisions -- many resources require a
  globally or regionally unique name, and `create_before_destroy` will
  fail immediately if the new resource's name collides with the one still
  being destroyed.
- Using `terraform apply -target` to push through just the replacement
  and dodge reviewing the full cascade can leave downstream resources
  referencing a stale ID from the destroyed resource until a full apply
  reconciles them.

## Verify
After applying the fix (or confirming the replacement is intentional and
safe), run `terraform plan` again and confirm either that the diff is now
`~` in-place instead of `-/+`, or -- if replacement is genuinely required
-- that the plan shows exactly the expected set of resources being
replaced with no unrelated resources swept into the cascade.
