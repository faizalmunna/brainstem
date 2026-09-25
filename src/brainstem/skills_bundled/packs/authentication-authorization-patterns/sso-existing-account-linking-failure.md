---
name: sso-existing-account-linking-failure
description: A user who already has a password-based account fails to log in via SSO even though the SSO provider returns the same verified email address.
triggers: ["sso login creates duplicate account", "google login says account already exists", "can't link sso to existing account", "email already registered error on oauth login", "sso and password login treated as different users"]
permissions: ["READ"]
---

## Symptom
A user who originally signed up with email/password tries "Sign in with Google" (or another SSO provider) using the same email address, and instead of logging into their existing account, they either get an "email already in use" error and are stuck, or -- worse -- a brand-new second account is silently created with the same email, splitting their data across two identities. New users who sign up via SSO from scratch work fine; the bug only shows up for accounts that pre-existed in another form.

## Likely causes
1. **Account lookup keys on the SSO provider's user ID, not email** -- the login handler queries `WHERE provider='google' AND provider_user_id=...`, finds no match (because the existing account was never linked to Google), and either errors or creates a new row instead of falling back to an email match.
2. **Email match exists but linking requires an explicit, separate step the flow never triggers** -- the code technically supports linking but only via a "connect account" button in account settings that a first-time SSO login never routes through.
3. **The SSO provider's email is trusted for matching without confirming it's verified** (`email_verified` claim), so either legitimate linking is blocked out of over-caution, or -- the opposite risk -- linking happens against an unverified email, letting an attacker who controls an unverified address on the IdP take over an existing account.
4. **Case or normalization mismatch** -- the existing account stored the email as typed at signup (mixed case, or with a `+alias`), while the IdP returns a normalized/lowercased version, so an exact-match query silently fails to find the existing row.
5. **Multiple SSO providers for the same email aren't reconciled** -- a user linked Google previously; logging in with Microsoft using the same email creates a second linkage or account because linking logic only checks for a match against the specific provider being used, not against the account's verified email across all providers.

## Diagnose
- Reproduce with a test account: sign up with email/password, then attempt SSO login with an IdP account sharing that exact email, and inspect the login handler's account-lookup query -- is it matching on provider+external ID first, and only falling back to email if that ID lookup fails?
- Check the IdP's token/userinfo response for `email_verified` and confirm the linking code actually branches on it (does it link automatically only when true, and require an explicit verification/step-up when false or absent?).
- Compare the stored email string in the database against the IdP-returned email byte-for-byte (case, whitespace, plus-addressing) for the failing account.
- Check whether the account/provider-link table has a unique constraint on `(user_id, provider)` vs `(provider, provider_user_id)` -- and whether a user can have multiple provider links pointing at one account, to see if the schema even supports linking multiple SSO providers to one existing account.
- Look for silent account creation: query for duplicate accounts sharing an email to confirm whether the bug produces an error or a duplicate row.

## Fix
On SSO login, look up the account by provider identity first; if no link exists yet, fall back to matching by normalized, verified email against existing accounts, and if a match is found, link the new provider identity to that existing account (recording the link) rather than creating a new one or rejecting the login -- but only auto-link when the IdP asserts the email is verified (`email_verified: true`); when it isn't, require the user to prove ownership another way (log in with the existing password first, or verify via a confirmation email) before linking, since auto-linking on an unverified email lets anyone who can register that address with the IdP hijack an existing account. Normalize email comparison consistently (lowercase, trim) on both write and read paths, and support multiple provider links per account via a many-to-one link table rather than a single provider column on the user row.

## Pitfalls
Auto-linking purely on email match without checking `email_verified` is a common "fix" for the linking failure that introduces an account-takeover path: an attacker registers an unverified address matching a victim's existing account email with the IdP and gets logged into the victim's account. Also, silently merging accounts on first SSO login without informing the user ("we linked your Google account to your existing account") can surprise users who intentionally wanted separate accounts (e.g. personal vs. work identity sharing a recovery email) -- surface the linking event, don't do it invisibly.

## Verify
Create a password-based test account, then complete SSO login with a provider account using the identical (verified) email, and confirm it logs into the *same* existing account (same user ID, same data) rather than erroring or creating a duplicate; separately, repeat with an IdP account whose email is unverified and confirm the flow requires additional proof of ownership rather than linking automatically.
