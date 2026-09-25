---
name: locale-format-assumed-in-form-validation
description: Form validation rejects legitimate international addresses, postal codes, phone numbers, or names because it hardcodes US-shaped format assumptions.
triggers: ["postal code validation rejects valid international address", "phone number field rejects non-US format", "form validation fails for foreign address", "zip code regex too strict for other countries", "name field rejects valid characters"]
permissions: ["READ"]
---

## Symptom
Users outside the country the form was originally designed for can't submit legitimate data: a postal code field rejects a Canadian or UK postcode because it requires exactly 5 digits, a phone number field rejects any number that isn't 10 digits with a US area code pattern, a "state/province" field is a hardcoded dropdown of US states with no option for non-US addresses, or a name field rejects a legally valid name containing an apostrophe, hyphen, or non-Latin script character because the validation regex only allows `[A-Za-z ]`. The user is completely blocked from proceeding (not just inconvenienced), which makes this a hard functional bug rather than a cosmetic one.

## Likely causes
1. **A validation regex or format assumption was written against the format the original developer/market was most familiar with** (5-digit US ZIP codes, `(XXX) XXX-XXXX` US phone numbers, `[A-Za-z]` name characters) without researching the actual variety of valid formats in other countries the product serves.
2. **Address forms hardcode a fixed field structure** (street/city/state-dropdown/zip) that assumes the US postal address model, which doesn't map onto address structures used elsewhere (many countries have no "state" equivalent, use postal-code-before-city ordering, or have address components in a different order/count entirely).
3. **Phone number validation assumes a fixed digit count and doesn't account for country code, varying national number lengths, or formatting characters** (spaces, dashes, parentheses) that are conventional in the number's country of origin but don't match a single hardcoded pattern.
4. **Name validation is written to allow only the Latin alphabet without diacritics** (a naive `[A-Za-z ]+` or `[A-Za-z\-']+` pattern), rejecting legally valid names containing accented characters, non-Latin scripts, or punctuation conventions the original regex author didn't anticipate.

## Diagnose
- Identify the exact field and regex/validation rule rejecting the input, and test it directly against a small set of known-valid real-world examples from several countries (a UK postcode like `SW1A 1AA`, a Canadian postal code like `K1A 0B1`, a German phone number, a name containing an apostrophe like "O'Brien" or a name in a non-Latin script) to see exactly which patterns fail.
- Check whether the field's format assumption is enforced client-side (regex in a form validator), server-side (a stricter or duplicate regex in the API), or both -- a bug can persist even after a client-side fix if the server independently re-validates with the old pattern.
- For address forms, check whether the field structure itself (not just per-field validation) assumes a US-shaped address (a mandatory "state" dropdown limited to US states, a mandatory fixed-length zip) rather than adapting fields shown/required based on the selected country.
- Check whether phone number validation distinguishes "digits only, fixed length" from a real phone-number-parsing library that understands per-country numbering plans (which vary in length and structure) -- a fixed digit count is a strong signal of the underlying bug.

## Fix
Replace hardcoded format assumptions with either country-aware validation logic or genuinely permissive validation plus downstream normalization: for phone numbers, use a maintained phone-number parsing library (e.g. Google's libphonenumber or a language binding of it) that validates against real per-country numbering plans rather than a fixed regex; for postal addresses, adapt the form's field set and validation rules based on the selected country (some countries have no state/province field, some have no postal code at all) instead of one fixed US-shaped template, and treat "address line" as a flexible enough field that unusual-but-valid structures aren't rejected; for name fields, validate permissively (reject only clearly invalid input like control characters) rather than allowlisting a specific script, since any character-class allowlist narrower than "matches what a passport or legal document would accept" will incorrectly reject real names.

## Pitfalls
- Loosening a name-field regex to allow "common European accented characters" but not broader Unicode name characters just moves the boundary of who gets incorrectly rejected rather than fixing the underlying assumption that a fixed allowlist is the right approach at all.
- Making a field "just accept anything" (removing validation entirely) to fix a rejection bug removes a real data-quality safeguard against genuinely malformed input (empty strings, injection attempts) -- the fix is validating against the actual real-world format variety, not abandoning validation.
- Fixing client-side validation but leaving a server-side duplicate validator with the old hardcoded pattern still blocks the same users at submission time, producing a confusing experience where the form appears to accept the input but the request still fails.

## Verify
Submit the form with a curated set of real, valid international examples covering at least three different countries' address/phone/name conventions (including at least one non-US postal code format, one non-US phone number format, and one name containing a diacritic or non-Latin script character) and confirm each is accepted end-to-end through both client-side validation and the server's independent validation, not just the client-side check.
