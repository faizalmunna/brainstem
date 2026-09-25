# Skill packs: authoring guide, quality bar, and roadmap

## Why packs exist

The project's own research explicitly warned against this failure mode
(see the plan, Q4): a huge pile of individually-named agents/skills that
are "namesake" -- a title and a one-line description, no real depth,
indistinguishable from each other in practice. That's the "repo hell"
this whole project is a reaction to.

A **pack** is a directory of skills for one real domain
(`skills/packs/<pack-name>/*.md`), discovered automatically by
`SkillRegistry` (see `src/brainstem/skills/registry.py`) -- adding a pack
never requires touching Python code. The point of the pack structure is
to make scaling toward genuine breadth (the long-term goal is comprehensive
coverage of major development environments, not a fixed number) tractable
without repeating the mistake above: each pack is authored depth-first,
against real, specific failure modes in that domain, not templated with a
name swapped in.

## Research grounding

Starting with the Data-domain packs (2026-09-20 onward), skill authoring
is seeded by real, publicly documented production incidents rather than
purely synthesized from general knowledge, specifically to keep the
"specific, recognizable symptom" bar honest at scale. The primary source
is [danluu/post-mortems](https://github.com/danluu/post-mortems), a
long-running, actively maintained curated collection of public
engineering postmortems from companies including GitHub, Amazon/AWS,
Cloudflare, GitLab, Discord, incident.io, CircleCI, Google, and many
others -- covering exactly the domains this library targets (databases,
caching, streaming, Kubernetes, CI/CD, distributed systems, networking).
Also referenced: [snakescott/awesome-tech-postmortems](https://github.com/snakescott/awesome-tech-postmortems).

This is used as **grounding for realistic root causes and diagnostic
detail**, not as source text to copy: every skill's prose (Symptom/
Likely causes/Diagnose/Fix/Pitfalls/Verify) is written fresh, generalized
into a reusable pattern rather than a single company's specific incident
narrative. Where a skill's root cause traces recognizably to a public,
named incident (e.g. "GitHub's ZooKeeper reprovisioning electing a
second leader and creating two Kafka clusters" is real, public, and
documented in GitHub's own engineering blog), that's a sign the failure
mode is real and worth including, not something to cite verbatim
paragraph-by-paragraph. This keeps the library's "premium, not
namesake" bar grounded in verifiable reality rather than plausible-
sounding invention, which matters more as pack count scales into the
hundreds.

## The quality bar

A skill earns a place in a pack only if it passes all of these. If it
doesn't, it's namesake bloat and shouldn't be added.

1. **Names a specific, recognizable symptom**, not a topic area. "React
   performance" is a topic. "A component re-renders on every keystroke in
   a sibling input" is a symptom someone can recognize themselves having.
2. **Gives more than one plausible root cause**, because real debugging
   rarely has exactly one culprit, and a skill that assumes the first
   guess is right teaches the wrong instinct.
3. **Gives concrete diagnostic steps** an agent can actually execute
   (a specific devtool, a specific query, a specific log line to look
   for) -- not "investigate the issue further."
4. **States the fix as a pattern, not a snippet to copy-paste blind** --
   the reasoning for *why* the fix works, so it generalizes past the exact
   example.
5. **Names at least one real pitfall/anti-pattern** people actually hit
   when applying the fix (over-memoizing, breaking accessibility while
   "fixing" a re-render, etc.).
6. **Says how to verify the fix actually worked** -- a specific check, not
   "test it."
7. **Is distinguishable from every other skill in its pack** -- if you
   can't explain in one sentence why this skill isn't a duplicate of
   another one in the same pack, don't add it.

Skills use the same manifest format as any other skill (see
`skills/repo-exploration.md` for the minimal example):

```markdown
---
name: kebab-case-unique-name
description: One sentence, specific enough to distinguish it from siblings in this pack.
triggers: ["phrase someone would actually type or say", "another one"]
permissions: ["READ"]
---

## Symptom
...
## Likely causes
...
## Diagnose
...
## Fix
...
## Pitfalls
...
## Verify
...
```

## Current packs (992 skills across 92 packs, last updated 2026-09-21 -- entire original roadmap taxonomy fully complete: Frontend & mobile, Backend languages & frameworks, QA/Testing, Infra/DevOps/Cloud, Data, Languages/build tooling, Security deep-dive, AI/ML Engineering, Cross-cutting Performance & Distributed Systems, and Misc high-value all 100% done)

Run `brainstem skills --packs --path .` for the live, authoritative count --
the table below is a snapshot and will drift as packs are added; the
roadmap section right after this is the source of truth for what's
checked off.

| Pack | Skills | Covers |
|---|---|---|
| `frontend-react` | 12 | React/Next.js rendering, state, performance, SSR boundary bugs, testing |
| `vue-nuxt` | 12 | Vue 3 reactivity, Nuxt SSR/hydration, data fetching, Pinia |
| `svelte-sveltekit` | 12 | Svelte 5 runes, SvelteKit load/actions/SSR |
| `angular` | 13 | Change detection, DI, RxJS/signals interop |
| `css-layout-debugging` | 13 | Flexbox/grid/stacking-context/positioning bugs (framework-agnostic) |
| `web-performance-vitals` | 13 | Core Web Vitals (LCP/INP/CLS/TTFB) root causes |
| `accessibility-wcag` | 12 | WCAG failures: focus, ARIA, contrast, keyboard operability |
| `react-native` | 14 | Native bridge, navigation, platform-specific bugs |
| `flutter-dart` | 12 | Widget rebuild storms, state management, platform channels |
| `pwa-offline` | 8 | Service worker staleness, offline sync, install prompts |
| `backend-api-design` | 10 | REST/GraphQL API design, auth, idempotency, migrations (FastAPI/Django-oriented) |
| `nodejs-express` | 12 | Event loop blocking, middleware ordering, memory leaks |
| `ruby-rails` | 12 | ActiveRecord N+1, callbacks, background job gotchas |
| `go-backend-services` | 14 | Goroutine leaks, context cancellation, error wrapping |
| `grpc-protobuf` | 12 | Schema evolution, streaming, deadline propagation |
| `java-spring-boot` | 12 | Bean lifecycle, transaction boundaries, classloading |
| `dotnet-aspnet` | 12 | Middleware pipeline, async deadlocks, EF Core pitfalls |
| `php-laravel` | 12 | Eloquent pitfalls, queue workers, config caching |
| `background-job-systems` | 12 | Celery/Sidekiq/BullMQ-style queue mechanics |
| `authentication-authorization-patterns` | 12 | OAuth/OIDC/session-vs-token mechanics |
| `python-async-concurrency` | 12 | asyncio pitfalls, GIL, threading vs multiprocessing |
| `qa-playwright` | 10 | E2E flakiness, locator strategy, network mocking, visual regression |
| `cypress-e2e` | 10 | Cypress-specific retry/intercept/session pitfalls |
| `unit-testing-javascript` | 14 | Jest/Vitest mocking, snapshot, timer, async pitfalls |
| `unit-testing-python` | 10 | pytest fixture/mocking/parametrize pitfalls |
| `unit-testing-java` | 12 | JUnit 5/Mockito lifecycle and mocking pitfalls |
| `contract-testing-pact` | 9 | Consumer-driven contract testing failure modes |
| `load-performance-testing` | 8 | k6/Locust/JMeter methodology mistakes |
| `mutation-testing-quality` | 7 | Test-suite-quality auditing beyond coverage |
| `test-data-management` | 10 | Fixtures/factories/seed-data strategy |
| `security-owasp` | 10 | OWASP Top 10 triage |
| `infra-containers-k8s` | 8 | Docker/Kubernetes deployment failure modes |
| `aws-failure-modes` | 15 | Lambda/S3/RDS/ECS/IAM/VPC-specific mechanics |
| `gcp-failure-modes` | 9 | Cloud Run/BigQuery/Pub-Sub/GKE/IAM-specific mechanics |
| `azure-failure-modes` | 14 | App Service/AKS/Functions-specific mechanics |
| `terraform-iac-deep` | 14 | State locking, drift, module design, workspace safety |
| `cicd-pipeline-design` | 13 | Deployment strategies, rollback safety, pipeline gating |
| `helm-kubernetes-packaging` | 12 | Chart structure, values sprawl, upgrade/rollback mechanics |
| `service-mesh-istio` | 11 | Sidecar injection, traffic policy, mTLS debugging |
| `incident-response-oncall` | 11 | Postmortems, alerting design, escalation, ownership |
| `secrets-management-vault` | 8 | Vault/KMS rotation, lease expiry, dynamic secrets |
| `cloud-cost-optimization` | 8 | Runaway spend diagnosis across providers |
| `observability` | 11 | Tracing, logging, alerting, SLOs |
| `data-postgres` | 8 | Query performance, connection pooling, transaction isolation |
| `mysql-specific` | 12 | MySQL nuances vs. Postgres assumptions |
| `mongodb-nosql` | 15 | Document modeling, index selection, aggregation pitfalls |
| `dynamodb-nosql` | 12 | Single-table design, hot partitions, GSI pitfalls |
| `redis-deep` | 7 | Data structures, cluster/failover, eviction policy |
| `kafka-streaming` | 11 | Partition assignment, consumer lag, exactly-once pitfalls |
| `elasticsearch-search` | 12 | Mapping design, relevance tuning, shard sizing |
| `data-pipelines-airflow-dbt` | 14 | DAG design, backfills, idempotency |
| `data-warehouse-query-optimization` | 12 | Snowflake/BigQuery/Redshift query patterns |
| `monorepo-turborepo` | 8 | Turborepo/Nx cache misses, task-graph ordering |
| `bazel-build-system` | 8 | Hermetic builds, remote cache misses, dependency handling |
| `golang-idioms-pitfalls` | 11 | Interface misuse, error handling, slice aliasing |
| `rust-systems-programming` | 15 | Borrow checker friction, unsafe pitfalls, async runtime choice |
| `typescript-type-system` | 14 | Generics, narrowing, structural typing surprises |
| `python-packaging-dependency-hell` | 6 | Version pinning, resolver conflicts, wheel issues |
| `dependency-upgrade-strategy` | 8 | Major-version bumps, changelog triage, canary rollout |
| `general` | 2 | How-to-use-brainstem meta-skills (not domain skills) |

Run `brainstem skills --packs --path .` to see live counts, or
`brainstem skills --pack <name> --path .` to browse one pack.

**Every skill above was written and reviewed against the quality bar in
this document, not generated from a template with a name swapped in** --
each names a specific symptom, gives multiple plausible root causes,
concrete diagnostic steps, a fix explained as a pattern (not just a
snippet), a named pitfall, and a verification step. This is the
"depth-first, prove it on a few domains" wave; see the roadmap below for
what's still unchecked.

## Roadmap: full domain taxonomy (target: 1000+ skills)

This is the honest target list toward comprehensive coverage of major
development environments, organized as an explicit, checkable pack
worklist rather than promised as a single undifferentiated blob. Each
line is `[ ] pack-directory-name -- domain (~N skills)`. Checked items
are built and passing `tests/test_skill_library_quality.py` (the
automated gate: no duplicate skill names anywhere in the library, every
pack skill has the full 6-section quality-bar structure, every
description is a real symptom sentence, not a bare topic label).

**Frontend & mobile**
- [x] `frontend-react` -- React/Next.js (12, wave 1)
- [x] `vue-nuxt` -- Vue 3/Nuxt rendering, reactivity, composables (12)
- [x] `svelte-sveltekit` -- Svelte 5 runes, SvelteKit load/actions (12)
- [x] `angular` -- change detection, DI, RxJS/signals interop (13)
- [x] `css-layout-debugging` -- flexbox/grid/stacking-context failures (13)
- [x] `web-performance-vitals` -- Core Web Vitals (LCP/INP/CLS) root causes (13)
- [x] `accessibility-wcag` -- WCAG failures beyond a single note in frontend-react (12)
- [x] `react-native` -- native bridge, navigation, platform-specific bugs (14)
- [x] `flutter-dart` -- widget rebuild storms, state management, platform channels (12)
- [x] `pwa-offline` -- service workers/offline (8, wave 1)

**Backend languages & frameworks**
- [x] `backend-api-design` -- REST/GraphQL, FastAPI/Django-oriented (10, wave 1)
- [x] `nodejs-express` -- event loop blocking, middleware ordering, memory leaks (12)
- [x] `ruby-rails` -- ActiveRecord N+1, callbacks, background job gotchas (12)
- [x] `go-backend-services` -- goroutine leaks, context cancellation, error wrapping (14)
- [x] `grpc-protobuf` -- schema evolution, streaming, deadline propagation (12)
- [x] `java-spring-boot` -- bean lifecycle, transaction boundaries, classloading (12)
- [x] `dotnet-aspnet` -- middleware pipeline, async/await deadlocks, DI scopes (12)
- [x] `php-laravel` -- Eloquent pitfalls, queue workers, config caching (12)
- [x] `background-job-systems` -- Celery/Sidekiq/BullMQ standalone pack (12)
- [x] `authentication-authorization-patterns` -- OAuth/OIDC/session-vs-token deep pack (12)
- [x] `python-async-concurrency` -- asyncio pitfalls beyond web-framework-specific ones (12)

**QA/Testing**
- [x] `qa-playwright` -- E2E/Playwright (10, wave 1)
- [x] `cypress-e2e` -- Cypress-specific pitfalls beyond the migration skill (10)
- [x] `unit-testing-javascript` -- Jest/Vitest mocking, snapshot, flake (14)
- [x] `unit-testing-python` -- pytest fixtures, mocking, parametrize pitfalls (10)
- [x] `unit-testing-java` -- JUnit/Mockito lifecycle and mocking pitfalls (12)
- [x] `contract-testing-pact` -- consumer-driven contract testing failures (9)
- [x] `load-performance-testing` -- k6/Locust/JMeter methodology and misreads (8)
- [x] `mutation-testing-quality` -- test-suite-quality auditing (7)
- [x] `test-data-management` -- fixtures/factories/seed-data strategy beyond one Playwright skill (10)

**Infra/DevOps/Cloud**
- [x] `infra-containers-k8s` -- Docker/K8s (8, wave 1)
- [x] `aws-failure-modes` -- Lambda/S3/RDS/ECS-specific failure modes (15)
- [x] `gcp-failure-modes` -- Cloud Run/BigQuery/Pub-Sub-specific failure modes (9)
- [x] `azure-failure-modes` -- App Service/AKS/Functions-specific failure modes (14)
- [x] `terraform-iac-deep` -- module design, state locking, drift beyond 1 skill (14)
- [x] `cicd-pipeline-design` -- pipeline architecture, deployment strategies, rollback (13)
- [x] `incident-response-oncall` -- postmortems, alerting design, escalation, full pack (11)
- [x] `helm-kubernetes-packaging` -- Helm chart pitfalls, values sprawl, upgrades (12)
- [x] `service-mesh-istio` -- sidecar injection, traffic policy, mTLS debugging (11)
- [x] `secrets-management-vault` -- Vault/KMS rotation, lease expiry, dynamic secrets (8)
- [x] `cloud-cost-optimization` -- runaway spend diagnosis across providers (8)
- [x] `observability` -- tracing/logging/alerting/SLOs (11, wave 2)

**Data** -- category complete, 8/8
- [x] `data-postgres` -- Postgres (8, wave 1)
- [x] `mysql-specific` -- MySQL-specific differences from Postgres assumptions (12)
- [x] `mongodb-nosql` -- document modeling, index selection, aggregation pitfalls (15)
- [x] `dynamodb-nosql` -- single-table design, hot partitions, GSI pitfalls (12)
- [x] `data-pipelines-airflow-dbt` -- DAG design, backfills, idempotency (14)
- [x] `data-warehouse-query-optimization` -- Snowflake/BigQuery/Redshift query patterns (12)
- [x] `redis-deep` -- data structures, cluster/failover, eviction policy beyond 1 skill (7)
- [x] `kafka-streaming` -- partition assignment, consumer lag, exactly-once pitfalls (11)
- [x] `elasticsearch-search` -- mapping design, relevance tuning, shard sizing (12)

**Languages/build tooling/cross-cutting engineering**
- [x] `monorepo-turborepo` -- Turborepo/Nx (8, wave 1)
- [x] `bazel-build-system` -- hermetic build failures, remote cache misses (8)
- [x] `golang-idioms-pitfalls` -- interface misuse, error handling, slice aliasing (11)
- [x] `rust-systems-programming` -- borrow checker friction, unsafe pitfalls, async runtime choice (15)
- [x] `typescript-type-system` -- generics, narrowing, structural typing surprises (14)
- [x] `python-packaging-dependency-hell` -- version pinning, resolver conflicts, wheel issues (6 of ~10, wave 1)
- [x] `dependency-upgrade-strategy` -- major-version bumps, changelog triage, canary rollout (8)
- [x] `legacy-code-migration` -- strangler-fig patterns, seam-finding, characterization tests (9)
- [x] `code-review-heuristics` -- what to actually look for, common blind spots (9)

**Security deep-dive** (beyond the OWASP triage in `security-owasp`) -- category complete, 8/8
- [x] `security-owasp` -- OWASP Top 10 triage (10, wave 1)
- [x] `sast-dast-tooling` -- static/dynamic scan setup, triage, false-positive handling (12)
- [x] `penetration-testing-methodology` -- scoping, recon, reporting discipline (8)
- [x] `cloud-security-posture` -- IAM over-permissioning, misconfigured storage, drift (15)
- [x] `container-security` -- image scanning, runtime hardening, escape vectors (11)
- [x] `api-security-deep` -- rate limiting, API key lifecycle, mass-assignment beyond OWASP basics (12)
- [x] `compliance-gdpr-soc2` -- data-handling/audit-trail gaps engineers actually hit (7)
- [x] `supply-chain-security` -- dependency confusion, typosquatting, SBOM gaps (9)
- [x] `threat-modeling` -- STRIDE-style review gaps, trust-boundary mistakes (9)

**AI/ML engineering** (this project's own domain -- high relevance) -- category complete, 8/8
- [x] `llm-prompt-engineering-pitfalls` -- prompt fragility, injection, format drift (14)
- [x] `rag-retrieval-debugging` -- chunking, embedding mismatch, retrieval precision (15)
- [x] `ml-model-serving-inference` -- latency, batching, cold starts, versioning (7)
- [x] `ml-data-pipeline-quality` -- label leakage, train/serve skew, data drift (12)
- [x] `vector-database-tuning` -- index choice, recall/latency tradeoffs, filtering (11)
- [x] `agent-tool-calling-reliability` -- malformed calls, loops, hallucinated tools (12)
- [x] `ml-training-fine-tuning-pitfalls` -- overfitting, catastrophic forgetting, eval leakage (12)
- [x] `ml-monitoring-drift-detection` -- silent model degradation in production (7)

**Cross-cutting performance & distributed systems** -- category complete, 8/8
- [x] `performance-profiling-methodology` -- language-agnostic profiling discipline (12)
- [x] `memory-leak-diagnosis` -- heap growth across GC'd and non-GC'd languages (6)
- [x] `concurrency-race-conditions` -- data races, deadlocks, lock ordering (12)
- [x] `distributed-systems-consistency` -- eventual consistency, split-brain, idempotency (12)
- [x] `caching-strategy-design` -- cache invalidation, stampede, staleness tradeoffs (11)
- [x] `api-versioning-strategy` -- breaking-change rollout, deprecation, client compat (7)
- [x] `websockets-realtime` -- reconnection storms, backpressure, fan-out scaling (11)
- [x] `graphql-deep` -- N+1 resolvers, schema stitching, persisted queries beyond API-design basics (12)

**Misc high-value**
- [x] `serverless-lambda-patterns` -- cold starts, concurrency limits, event-source pitfalls (~10)
- [x] `desktop-electron-apps` -- IPC pitfalls, packaging, auto-update failures (~8)
- [x] `cli-tool-design` -- argument parsing, exit codes, piping/composability (~8)
- [x] `localization-i18n` -- pluralization, RTL, encoding, date/currency pitfalls (~10)
- [x] `payment-processing-billing` -- idempotent charges, webhook reliability, proration (~10)
- [x] `email-deliverability` -- SPF/DKIM/DMARC failures, bounce handling, spam triage (8)

## How to add the next pack

1. Pick one unchecked item above.
2. Write 8-15 skills against the quality bar, not a target count --
   depth over hitting a number.
3. Add the pack row to the "Current packs" table and check its box here.
4. Run `uv run pytest tests/test_skills.py tests/test_skill_library_quality.py`
   and `brainstem skills --packs` to confirm it's discovered and passes
   the automated duplicate-name/structure/description gate.
