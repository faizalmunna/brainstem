---
name: stale-locale-timezone-inferred-once
description: A user's locale or timezone was inferred once from IP geolocation or a cached session and never updated, so localized dates and content stay wrong after they travel or move.
triggers: ["wrong timezone after traveling", "dates showing wrong time after moving", "locale stuck on old country", "cached timezone not updating", "IP geolocation timezone wrong for VPN user"]
permissions: ["READ"]
---

## Symptom
A user's displayed times, dates, or language consistently reflect a location or locale they're no longer in: someone who traveled from New York to London still sees times in Eastern time, a user who moved countries permanently still gets content in their old country's language/currency, or a user on a VPN or corporate proxy sees content localized to the VPN exit node's country instead of their actual one. The behavior is often "sticky" -- it doesn't recover on its own even after the user's actual context clearly changes, which points to the value being determined once and cached rather than recomputed.

## Likely causes
1. **Locale/timezone is inferred from IP geolocation at signup or first login and stored permanently** on the user's profile/session, with no mechanism to re-infer or prompt for correction later, so it reflects wherever the user happened to be at that one moment indefinitely.
2. **The value is cached in a session, JWT claim, or server-side cache with a long or no expiry**, so even if the inference logic itself is re-run periodically elsewhere, the cached stale value is what's actually read on each request until the cache/session is invalidated.
3. **IP geolocation is inherently unreliable for a meaningful fraction of users** -- VPNs, corporate proxies, mobile carrier NAT gateways, and satellite ISPs routinely geolocate to a different city, region, or country than the user's actual physical location, and the system has no fallback or correction path when this happens.
4. **The client's local timezone/locale (available via `Intl.DateTimeFormat().resolvedOptions().timeZone` or the OS locale) is read once on first load/install and never re-checked**, so a mobile app that correctly detected the timezone at install time keeps using that value even after the device's actual timezone changes (travel, or the OS timezone setting changing).
5. **Timezone and locale (language/region formatting preference) are conflated as one inferred value**, when they're independent axes that can each be wrong for different reasons -- a business traveler wants their timezone updated live but very likely does *not* want their display language auto-switched every time they cross a border.

## Diagnose
- Determine where the value is actually read from at request/render time -- a database column, a session/cookie, a JWT claim, an in-memory cache -- and check that source's actual freshness (when it was last written, whether it has a TTL) versus assuming it's recomputed live.
- Reproduce by simulating a location or timezone change (change the client OS timezone, or make a request from a different IP/VPN exit) and observe whether the displayed timezone/locale updates on the very next request, after a delay, or not at all -- this tells you whether it's cached, batch-refreshed, or truly static.
- Check whether the product distinguishes an explicit user-set preference (a settings-page timezone/language choice) from an inferred default -- if both are stored in the same field, an inference refresh can incorrectly overwrite something the user deliberately set.
- For IP-geolocation-based inference specifically, test with a known VPN/proxy IP and confirm whether the system has any signal to detect or discount an unreliable geolocation (e.g. IP flagged as a known VPN/datacenter range) versus trusting every IP lookup equally.

## Fix
Treat locale and timezone as two independent, live pieces of context rather than one inferred-once profile field: prefer the client's live-reported timezone (`Intl.DateTimeFormat().resolvedOptions().timeZone` client-side, refreshed on each session or app foreground) over server-side IP geolocation whenever a client is available to report it directly, since the client always knows its own current timezone with certainty while IP geolocation is only a proxy guess. Keep an explicit, user-editable timezone/locale setting that -- once set by the user -- takes priority over any inference and is never silently overwritten by a fresh geolocation lookup; only fall back to (re-)inferring when there's no explicit user preference stored. Where IP geolocation is the only available signal (e.g. for anonymous/pre-login content), recompute it per-request or per-session rather than caching it indefinitely, and treat it as a low-confidence default that's cheap to override, not a fact to persist permanently.

## Pitfalls
- Auto-updating timezone from live client signals but also auto-updating display *language* the same way produces a worse experience for legitimate travelers or VPN users who want their clock correct but their language stable -- these two settings need independent update policies, not one combined "locale" blob refreshed together.
- Re-inferring and silently overwriting a value the user explicitly set in a settings page (because the inference job doesn't check for an explicit override flag) undoes a deliberate user choice and will recur every time the inference job runs, appearing to the user as a setting that "won't stick."
- Trusting IP geolocation as ground truth without accounting for known-unreliable IP ranges (VPNs, corporate NAT, mobile carrier CGNAT) causes confidently wrong localization for exactly the users most likely to notice and be annoyed by it (frequent travelers, remote workers using a VPN).

## Verify
Simulate a context change end-to-end -- change the test client's OS/browser timezone (or connect from a different network/VPN egress for IP-based inference) -- and confirm the displayed timezone updates within one session/request cycle without requiring the user to manually reset anything, while separately confirming that a timezone or locale the user explicitly set in settings is preserved and not overwritten by that same inference pass.
