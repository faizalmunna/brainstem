---
name: release-build-signing-failure
description: Fix a release build that fails to produce a signed APK, AAB, or IPA due to keystore, provisioning profile, or certificate misconfiguration.
triggers: ["keystore not found error", "gradle signing config failed", "no signing certificate found xcode", "provisioning profile doesn't match", "release build fails to sign"]
permissions: ["READ"]
---

## Symptom
A debug build works fine, but generating a release artifact for
distribution fails during the signing step -- Gradle errors like
"Keystore file ... not found" or "Failed to read key from keystore," or
Xcode/`xcodebuild`/Fastlane errors like "No signing certificate found,"
"Provisioning profile doesn't match the entitlements," or "code signing
is required" -- and the build never produces an installable/uploadable
artifact.

## Likely causes
1. **Keystore file or credentials missing/misreferenced (Android)** --
   `android/gradle.properties` or `android/app/build.gradle` references
   a keystore path, alias, and passwords that don't match what's actually
   present on the build machine (common in CI, where the keystore file
   itself isn't checked into the repo and wasn't provisioned in the CI
   environment, or a local `local.properties`/env-var override exists on
   one machine but not another).
2. **Provisioning profile / certificate mismatch (iOS)** -- the
   provisioning profile referenced doesn't include the entitlements
   actually used by the app (push notifications, associated domains,
   app groups added later without regenerating the profile), or the
   signing certificate has expired, was revoked, or belongs to a
   different Apple Developer Team than the profile.
3. **Automatic signing (Xcode "Automatically manage signing") fighting
   with a CI environment that has no interactive Apple ID session** --
   works fine locally where Xcode can silently refresh certificates/
   profiles via a logged-in account, fails in CI where no such session
   exists and manual/fastlane-match-style signing is actually required.
4. **Bundle identifier or package name mismatch** -- the app's actual
   `applicationId`(Android)/`bundle identifier` (iOS) doesn't match what
   the provisioning profile or Play Console app listing expects, often
   after a rename or when a build variant/flavor appends a suffix (e.g.
   `.debug`) that leaks into what should be the release identifier.
5. **A recently expired certificate or keystore validity window** --
   Android keystores and iOs distribution certificates have expiration
   dates; a build that worked for months suddenly failing is often
   exactly this, especially right after a certificate's multi-year
   validity period lapses.

## Diagnose
- Read the exact error text carefully -- Gradle and Xcode signing errors
  are usually specific about which file/alias/profile/certificate is the
  problem, not generic; resist jumping to a full clean before reading it.
- For Android, run `keytool -list -v -keystore <path> -alias <alias>`
  with the configured password to confirm the keystore file exists, the
  alias is correct, and check the printed validity dates for expiration.
- For iOS, open Xcode's Signing & Capabilities tab for the release
  configuration/scheme and check for a red error indicator naming the
  exact missing capability/profile mismatch, or run `security
  find-identity -v -p codesigning` to list valid signing identities
  currently available in the keychain.
- In CI specifically, confirm the keystore/certificate/profile files were
  actually provisioned into the CI environment (as a secret file, base64
  env var decoded to a file, etc.) and that the decode/placement step
  ran before the build step, rather than assuming a config that works
  locally will "just work" in CI.
- Check the Apple Developer portal / Google Play Console directly for
  certificate/profile expiration or revocation status rather than
  inferring it purely from the local error message.

## Fix
- Store the keystore file securely (never in plain source control) and
  reference it via environment variables or a CI secrets mechanism,
  ensuring the exact same path/alias/password combination is used in
  every environment that needs to sign a release build -- document this
  setup so it survives a team member leaving or a new CI runner being
  provisioned.
- For iOS, use a deterministic signing strategy for CI (Fastlane
  `match`, or manually managed profiles checked into a secure private
  repo) instead of relying on Xcode's automatic signing, which assumes
  an interactive, authenticated Xcode session that CI doesn't have.
- Regenerate the provisioning profile whenever new entitlements/
  capabilities are added to the app (push, associated domains, app
  groups) -- profiles are a snapshot of capabilities at creation time and
  don't auto-update when the app's `entitlements` file changes.
- Align the bundle identifier/`applicationId` used in the build
  configuration exactly with what the provisioning profile/Play Console
  listing expects, watching specifically for build-variant suffixes that
  should only apply to debug/staging flavors.
- Renew expiring certificates/keystores proactively (calendar the
  expiration dates) rather than discovering the expiration only when a
  release build unexpectedly fails.

## Pitfalls
- Regenerating a *new* Android keystore because the original was lost or
  its password forgotten breaks the ability to publish updates to an app
  already live on the Play Store, since Play requires the same signing
  key (or Play App Signing enrollment) for updates -- treat keystore loss
  as a serious incident requiring Play App Signing recovery options, not
  a "just make a new one" fix.
- Toggling Xcode to "Automatically manage signing" to make a local error
  go away can silently create a new, different profile/certificate than
  the one CI or teammates expect, causing the next CI build or another
  developer's build to fail instead -- coordinate signing strategy across
  the whole team/CI, not per-developer-machine.

## Verify
Produce a full, distributable signed artifact (a signed `.aab`/`.apk` via
`./gradlew bundleRelease`/`assembleRelease`, or a signed `.ipa` via
`xcodebuild archive` + export, or the equivalent EAS Build command) from
a clean checkout (not an already-configured local machine) and confirm
it installs on a device or uploads successfully to the Play Console
internal track / TestFlight without a signing-related rejection.
