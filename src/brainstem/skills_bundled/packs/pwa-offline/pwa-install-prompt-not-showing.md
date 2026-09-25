---
name: pwa-install-prompt-not-showing
description: Diagnose why a PWA's "Add to Home Screen"/install prompt isn't appearing even though the app is intended to be installable.
triggers: ["add to home screen not showing", "pwa install prompt missing", "beforeinstallprompt not firing", "pwa not installable", "install button not appearing"]
permissions: ["READ"]
---

## Symptom
The browser's install prompt (or the app's own custom "Install" button
relying on the `beforeinstallprompt` event) never appears, even though the
app is intended to meet installability criteria and works fine as a
regular web page.

## Likely causes
1. **The web app manifest is missing required fields or isn't linked
   correctly** -- installability requires a valid `manifest.json` (or
   `.webmanifest`) linked via `<link rel="manifest">`, with required
   fields like `name`/`short_name`, `start_url`, `display` (typically
   `standalone` or `fullscreen`), and appropriately-sized icons.
2. **No registered, active service worker** -- most browsers require an
   active service worker (even a minimal one) as an installability
   signal, distinct from actually needing offline support for the prompt
   to appear.
3. **Served over an insecure origin** -- installability (and service
   workers generally) require HTTPS (or `localhost` for local
   development); an app served over plain HTTP in a non-local environment
   won't be installable regardless of manifest/service-worker
   correctness.
4. **The browser's own installability heuristics not met** -- some
   browsers require a minimum engagement threshold (the user has visited
   the site a couple of times, or spent a minimum amount of time) before
   showing the prompt, which can look identical to "not installable" on a
   first visit during testing.
5. **The app was already installed (or previously dismissed) in this
   browser profile**, suppressing the prompt for a cooldown period or
   until uninstalled -- easy to mistake for a configuration bug when
   testing repeatedly in the same browser profile.

## Diagnose
- Use the browser devtools' Application/Manifest panel (Chrome/Edge) to
  check for explicit manifest validation errors and confirm all required
  fields are present and correctly typed.
- Check the Application/Service Workers panel to confirm a service worker
  is registered and active for the current origin, not just present in
  source code.
- Confirm the app is served over HTTPS (or `localhost`) in the
  environment being tested.
- Test in a fresh browser profile/incognito window to rule out a
  previous install/dismissal suppressing the prompt in the current
  profile.
- Check whether the specific browser being tested has an engagement-based
  heuristic (varies by browser/version) that a single fresh page load
  wouldn't satisfy.

## Fix
- Fix any manifest validation errors reported by devtools, and ensure all
  required fields (`name`, `short_name`, `start_url`, `display`, and
  icons meeting the browser's minimum size requirements) are present and
  correct.
- Register a service worker (even a minimal pass-through one, if offline
  support isn't the immediate goal) so the installability signal is met,
  separate from actual offline functionality.
- Ensure the production deployment serves over HTTPS.
- For custom install-button UX, correctly capture and defer the
  `beforeinstallprompt` event (store the event, call `.prompt()` later on
  user action) rather than assuming the browser's default prompt will
  appear automatically, since calling `event.preventDefault()` on
  `beforeinstallprompt` (needed for custom UX) suppresses the automatic
  prompt entirely and requires the app to trigger it manually.
- For engagement-heuristic-related delays during testing, don't conclude
  the setup is broken from a single fresh visit -- test the manifest/
  service-worker correctness directly via devtools rather than relying
  solely on whether the prompt appeared.

## Pitfalls
- Calling `event.preventDefault()` on `beforeinstallprompt` to build a
  custom install button, then never actually calling `.prompt()` on that
  saved event later, silently removes the install capability entirely
  (neither the default nor the custom prompt appears) -- a common
  mistake when adding custom install UX.
- Testing exclusively in a browser/profile where the app was already
  installed previously can make correctly-configured installability look
  broken -- always verify in a clean profile before concluding there's a
  real bug.

## Verify
In a fresh browser profile, load the app, confirm via devtools that the
manifest validates with no errors and a service worker is active, then
confirm the install prompt (default or custom) appears and successfully
installs the app when triggered.
