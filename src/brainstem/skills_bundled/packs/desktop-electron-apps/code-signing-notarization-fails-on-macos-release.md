---
name: code-signing-notarization-fails-on-macos-release
description: A macOS Electron build passes code signing but fails Apple notarization, or passes both but is still blocked by Gatekeeper on end-user machines.
triggers: ["electron macos notarization failed", "gatekeeper blocking electron app", "app signed but wont open macos", "macos build rejected by apple"]
permissions: ["READ"]
---

## Symptom

A macOS build of an Electron application either fails Apple's
notarization process during the release pipeline, or successfully
completes signing and notarization but is still blocked by Gatekeeper
("app is damaged and can't be opened," or a similar warning) when
end-users try to run it.

## Likely causes

- **A dependency or the Electron binary itself includes an unsigned or
  improperly-signed embedded binary/framework**, and Apple's
  notarization service rejects the whole package because every nested
  executable/library must be properly signed, not just the top-level
  app bundle.
- **Hardened runtime entitlements aren't correctly configured** for
  specific capabilities the application needs (JIT compilation, which
  Electron's V8 engine requires, or specific system permissions), causing
  either a notarization rejection or a runtime crash on end-user
  machines even after successful notarization.
- **The notarization ticket wasn't correctly "stapled" to the app bundle
  after notarization succeeded**, so offline or network-restricted
  end-user machines can't verify notarization status (which normally
  requires an online check) and Gatekeeper blocks the app as a result.
- **A build/packaging step modifies the app bundle after signing**
  (a post-processing step that touches files inside the bundle), which
  invalidates the signature, causing Gatekeeper to correctly detect
  tampering and block the app even though signing appeared to succeed
  earlier in the pipeline.

## Diagnose

1. Check the notarization submission's actual response/log for specific
   rejection reasons (Apple's notarization service provides a detailed
   log identifying exactly which nested binary or entitlement issue
   caused rejection).
2. Verify every binary/framework/library nested inside the app bundle is
   individually signed by checking each with the platform's code-signing
   verification tool, not just the top-level app.
3. Check the entitlements file used for signing against Electron's
   documented hardened-runtime requirements for the specific Electron
   version in use.
4. Confirm whether the notarization ticket was actually stapled to the
   bundle after notarization, and verify this on a machine without
   network access to simulate the end-user scenario that would surface a
   missing staple.

## Fix

Ensure the build pipeline signs every nested binary within the app
bundle (deep-signing, from the innermost binaries outward) before
signing and notarizing the top-level bundle, following Electron's
documented macOS packaging/notarization guidance for the specific
version and packaging tool in use. Configure hardened runtime
entitlements to match Electron's actual requirements (JIT entitlement in
particular is commonly needed). Explicitly staple the notarization
ticket to the app bundle as a required pipeline step after successful
notarization, and verify the stapling succeeded before considering the
release process complete. Ensure no build step modifies the bundle after
the final signing step.

## Pitfalls

Don't disable Gatekeeper or instruct users to bypass it (right-click-
open workarounds) as a substitute for actually fixing signing/
notarization -- that's a poor user experience and a red flag for
security-conscious users; fix the actual pipeline issue instead.

## Verify

Complete a full release build through the actual pipeline and verify
notarization success via Apple's own status-check tooling, confirm
stapling succeeded, and test launching the app on a genuinely separate,
clean macOS machine (ideally with no special developer configuration)
to confirm Gatekeeper allows it to run without any warning or bypass
needed.
