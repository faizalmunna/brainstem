# Security policy

Brainstem is local-first: its standard MCP transport is local stdio, the
default profile is read-only, and repository source is not exposed over a
network endpoint by default.

## Supported versions

Only the latest published release receives security fixes. Before the first
public release, the maintainer must add the real repository security-advisory
URL and a monitored private reporting address here; this source repository has
no verified public remote yet, so no guessed reporting channel is listed.

## Reporting

Do not publish proof-of-concept exploits, credentials, or sensitive repository
content in public issues. Until a verified advisory channel is configured,
report vulnerabilities directly to the repository owner through a private,
authenticated channel.

## Release controls

Production releases require a locked dependency install, tests on Windows,
Linux, and macOS, CodeQL analysis of the Python runtime and npm wrapper,
dependency-update review, an SBOM and provenance, and a review of MCP
permission or execution-boundary changes.

Generate the runtime SBOM from the reviewed lockfile with
`uv run brainstem sbom --path . --output sbom.cdx.json`. It includes default
runtime dependencies only unless an optional extra is explicitly selected.

For a `v*` tag, artifact creation waits for the security, Windows/Linux/macOS,
npm-install, and Docker CI checks. It then builds Python and npm artifacts and
requests signed provenance plus a CycloneDX SBOM attestation. It does not
publish; publishing remains a separate maintainer action after registry
identity and release policy are verified. Consumers should verify the signed
artifact before trusting it, for example with
`gh attestation verify <artifact> -R <owner/repository>` after the real
repository exists.
