# Security policy

Brainstem is local-first: its standard MCP transport is local stdio, the
default profile is read-only, and repository source is not exposed over a
network endpoint by default.

## Supported versions

Only the latest published release receives security fixes.

## Reporting

Do not publish proof-of-concept exploits, credentials, or sensitive repository
content in public issues. Report vulnerabilities privately through GitHub
Private Vulnerability Reporting at
https://github.com/faizalmunna/brainstem/security/advisories/new. Reports are
visible only to the repository maintainers and GitHub until the reporter and
maintainer agree to disclose them.

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
`gh attestation verify <artifact> -R faizalmunna/brainstem`.
