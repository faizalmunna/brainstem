---
name: secrets-baked-into-image-layer
description: A container image leaks an API key or private SSH key baked into an intermediate build layer even though a later step deletes the file before the final image.
triggers: ["docker history shows a secret file that was deleted", "we found an api key inside a pulled image using dive", "npm token leaked in docker image layers even after rm"]
permissions: ["READ"]
---

## Symptom
Someone runs `docker history` or a layer inspection tool (`dive`, `docker save | tar`) against a published image and finds a secret -- an npm/pip auth token, an SSH private key used to clone a private repo, a cloud credential -- sitting in an earlier layer, even though the Dockerfile has a later `RUN rm` step that deletes the file. Anyone who can `docker pull` the image can extract the secret from that layer regardless of later deletions, because layers are additive and immutable.

## Likely causes
1. **A secret is copied into the build context and used via `COPY`/`ARG`/`ENV` in a single-stage Dockerfile**, then deleted in a later `RUN` -- but each Dockerfile instruction creates its own layer, and deletion in a later layer doesn't remove the file's bytes from the earlier layer that's still part of the image.
2. **Build-time `ARG` values are assumed to be ephemeral**, but `ARG`-provided secrets are visible both in the image's layer history and in `docker inspect`/build cache metadata unless the build explicitly avoids persisting them.
3. **A private dependency (npm private registry, private pip index, git-over-SSH) requires a credential during `npm install`/`pip install`/`git clone`, and the credential file (`.npmrc`, `.netrc`, SSH key) is copied in for that one step** without using a mechanism that keeps it out of the final layer set entirely.
4. **No secret-scanning step in CI catches this before push** -- the image builds and passes functional tests, and the secret leak is only discovered later via manual inspection or, worse, via an actual credential-abuse incident.

## Diagnose
1. Pull the image and dump full layer history: `docker history --no-trunc myimage:tag` -- look for `COPY`/`ADD`/`RUN` commands referencing key/token/credential filenames.
2. Extract and grep every layer's filesystem diff directly (this is the ground truth, independent of what the final `docker run` filesystem shows): `dive myimage:tag` or manually `docker save myimage:tag -o img.tar && tar -xf img.tar` then grep each layer tarball for known secret patterns.
3. Check the Dockerfile for `ARG` declarations that receive secret-like values, and confirm whether `--build-arg` secrets show up in `docker inspect myimage:tag --format '{{.Config}}'` or CI build logs (both are common leak points independent of the layer-file issue).
4. Scan with a dedicated tool for confirmation and coverage: `trivy image --scanners secret myimage:tag` or `gitleaks` against the extracted layers.

## Fix
Use BuildKit's dedicated secret-mounting mechanism (`RUN --mount=type=secret,id=npmtoken`) so the credential is available only during that specific `RUN` step's execution and is never written into any committed layer at all -- this is different from deleting the file afterward, because the secret never becomes part of a layer's diff in the first place. For multi-stage builds, keep the credential-requiring install step in an early build stage and `COPY --from=` only the final built artifacts into the runtime stage, so the runtime image's layer history never includes the build stage's layers at all. Once a secret is confirmed baked into a *published* image, treat it as compromised: rotate the credential immediately, since deleting or overwriting the image tag does not retroactively remove it from anyone who already pulled it, and old layers may persist in registry caches or other tags sharing that layer.

## Pitfalls
Believing that squashing the image (`docker build --squash`) or deleting the file in a later layer "removes" the secret is a common and dangerous misconception -- squashing merges the visible final filesystem but the underlying secret bytes can still be reconstructed from registry-side layer storage or local build cache in many setups, and it does nothing to un-leak an image that's already been pulled by others. The only real fix after the fact is credential rotation, not image surgery.

## Verify
After switching to `--mount=type=secret`, rebuild and run `docker history --no-trunc` plus a `trivy image --scanners secret` pass on the new image to confirm zero secret-pattern matches across all layers. Separately, confirm the credential referenced in the old leaked image has actually been rotated at the source (registry/API provider) and that the old value now fails authentication.
