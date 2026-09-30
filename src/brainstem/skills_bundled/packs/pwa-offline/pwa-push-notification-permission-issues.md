---
name: pwa-push-notification-permission-issues
description: Diagnose low opt-in rates or broken push notification delivery in a PWA, often caused by requesting permission at the wrong time or a broken subscription/backend pipeline.
triggers: ["push notification permission denied", "low notification opt in rate", "push notification not received", "notification permission best practice", "service worker push not working"]
permissions: ["READ"]
---

## Symptom
Either most users deny (or ignore) the browser's notification permission
prompt, resulting in a low opt-in rate, or users who did grant permission
still don't receive push notifications that the backend believes it sent
successfully.

## Likely causes (low opt-in)
1. **Requesting permission immediately on page load**, before the user
   has any context for why notifications would be valuable -- browsers
   and users both treat an immediate, unexplained permission prompt as a
   strong signal to dismiss/deny, and most browsers can't re-prompt after
   a denial without the user manually changing site settings.
2. **No explanation of value before the browser's native prompt appears**
   -- asking for permission without first showing the user what they'd
   get (e.g. "get notified when your order ships") gives them no reason
   to say yes.

## Likely causes (permission granted but not delivered)
3. **The push subscription (endpoint + keys) generated client-side was
   never successfully sent to and stored by the backend**, so the server
   has nothing to send to even though the client believes it's subscribed.
4. **The subscription expired or was invalidated** (browser-side push
   service rotated the endpoint) without the client detecting this and
   re-subscribing, so the backend is sending to a now-dead endpoint.
5. **VAPID key mismatch** between what the client subscribed with and
   what the backend uses to send, causing the push service to reject the
   message silently from the backend's perspective (or the client to
   never have successfully subscribed in the first place).
6. **The service worker's `push` event handler has a bug** (throws,
   doesn't call `event.waitUntil` correctly) so even a successfully
   delivered push message fails to display a notification.

## Diagnose
- For opt-in rate, check *when* in the user journey the permission
  request is triggered -- immediately on load is the single most common,
  easily-checked cause.
- For delivery issues, check the backend's actual send response for the
  specific subscription (push services typically return an error/status
  code indicating an invalid or expired subscription, distinct from a
  generic "sent successfully").
- Check whether the client has any logic to detect subscription
  expiration/change (`pushsubscriptionchange` event) and re-register with
  the backend, or whether subscriptions are stored once and never
  refreshed.
- Check the service worker's `push` event listener directly for errors
  (test by manually triggering a push event in devtools where supported).

## Fix
- Request notification permission only after showing the user
  contextual, specific value (a custom in-app prompt explaining what
  they'll be notified about, with the user's own action triggering the
  actual browser permission request) rather than firing it unconditionally
  on load.
- Ensure the client reliably sends the push subscription details to the
  backend immediately after subscribing, with error handling/retry if
  that request fails, so a successful client-side subscription always
  results in a backend record.
- Listen for the `pushsubscriptionchange` event and re-subscribe/re-send
  to the backend when it fires, so expired/rotated subscriptions don't
  silently go stale.
- Verify VAPID key configuration matches exactly between client
  subscription code and backend send code, and handle backend send
  errors indicating an invalid/expired subscription by removing that
  subscription from the backend's records rather than retrying it
  indefinitely.
- Fix and test the service worker's `push` event handler in isolation
  (trigger a test push) to confirm it correctly displays a notification
  given a valid push event.

## Pitfalls
- Re-requesting permission repeatedly after a denial (via reload prompts,
  banners) doesn't work in most browsers (a denial typically requires the
  user to manually change site permissions) and can be perceived as
  harassment -- design for a single well-timed request, accept a "no," and
  offer another path to opt in later (a settings page toggle) rather than
  nagging.
- Storing only the latest subscription per user without handling
  multiple devices/browsers can silently drop notifications to a user's
  other devices when a new subscription overwrites an old one instead of
  being added alongside it.

## Verify
For opt-in rate, measure the actual grant rate before and after moving
the permission request to a contextual trigger point. For delivery,
send a real test push to a subscription created through the actual
client flow (not a manually-fabricated one) and confirm it's received and
displayed correctly, including after simulating a subscription
expiration/rotation.
