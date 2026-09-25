---
name: provider-upgrade-silent-behavior-change
description: A provider version upgrade changes the default behavior for an existing resource, producing an unexpected plan diff on the next apply with no code change.
triggers: ["terraform plan shows changes after provider upgrade", "no code changed but terraform wants to apply", "provider version bump broke plan", "unexpected diff after terraform init -upgrade", "terraform plan diff with no config change"]
permissions: ["READ"]
---

## Symptom
Nobody touched any `.tf` file, but after running `terraform init
-upgrade` (or a lockfile update pulls in a newer provider version),
`terraform plan` suddenly shows a diff -- attributes changing to new
default values, a previously-optional block now required, or a resource
being modified/replaced -- for resources whose configuration is
unchanged.

## Likely causes
1. **The provider changed a resource's default value for an
   unspecified argument** between versions -- when a `.tf` block doesn't
   set an argument explicitly, Terraform uses the provider's default, and
   if that default changes in a new provider release, the plan reflects
   the new default as a diff against the old state even though the
   config text never mentioned it.
2. **The provider changed how it reads/normalizes an attribute from the
   API** (e.g. previously stored a value in one casing/format and now
   normalizes it differently), producing a cosmetic-looking diff that's
   actually just a representation change, not a real infrastructure
   change.
3. **A resource schema version was bumped with an accompanying state
   upgrade function** that transforms old state shapes into new ones,
   and that transform doesn't perfectly preserve a value, or exposes a
   previously-hidden computed field that now shows as "known after
   apply."
4. **The lockfile (`.terraform.lock.hcl`) wasn't committed or was out of
   sync**, so different runs (a developer's laptop vs. CI) silently
   resolved to different provider versions on `init`, making the
   "silent" change actually a version-skew problem between environments
   rather than a genuine upstream default change.

## Diagnose
- Check `.terraform.lock.hcl` diff (if committed) or run `terraform
  version` alongside `terraform providers` to see exactly which provider
  version is now in use versus what was previously locked, before
  assuming the diff is a "real" infra change.
- Read the provider's CHANGELOG/release notes between the old and new
  version for the specific resource type in the diff -- search for
  "default," "breaking," or "behavior change" -- most well-maintained
  providers document default-value changes explicitly per version.
- Run `terraform plan -out=tfplan && terraform show -json tfplan` and
  check whether the changed attribute was ever set explicitly in the
  `.tf` config (absent from `configuration` in the JSON plan but present
  in the diff confirms it's a provider-default-driven change, not a
  config-driven one).
- Reproduce with the old provider version pinned (temporarily set an
  explicit `version` constraint matching the previous release in the
  `required_providers` block and re-run `init` and `plan`) to confirm the
  diff disappears, isolating the cause to the provider bump specifically.

## Fix
Once confirmed as a provider default change, decide explicitly rather
than letting the new default apply implicitly: either pin the
previously-implicit value explicitly in the resource configuration (so
future provider upgrades can't silently change it again), or accept the
new default deliberately and document why in the PR/commit that bumps
the provider version. Going forward, pin provider versions with a
narrow, deliberate constraint (e.g. `~> 5.3` rather than an open `>=`)
and always commit `.terraform.lock.hcl`, so provider upgrades are a
reviewed, intentional PR (bump lockfile, review the plan diff, merge)
rather than something that happens silently on whichever machine runs
`init` next.

## Pitfalls
- Widening a version constraint to "just get past" a CI failure caused by
  a provider bump, without reading the changelog, can pull in several
  more minor versions' worth of default changes at once, making the next
  diff much harder to attribute to a specific change.
- Applying the plan to "accept" the new defaults without first confirming
  whether the changed attribute has real infrastructure impact (e.g. a
  changed default that triggers `ForceNew` and thus resource recreation)
  can turn a cosmetic-looking provider bump into unplanned downtime.

## Verify
After pinning the value explicitly (or deliberately accepting the new
default and applying), run `terraform plan` again and confirm the diff is
gone -- a clean plan with the provider version bump merged is the
concrete signal that the behavior change has been resolved rather than
just deferred to the next `apply`.
