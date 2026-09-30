---
name: locale-number-input-parsed-with-wrong-separator
description: A numeric input field misinterprets the decimal or thousands separator a user typed, silently turning a typed value into a number 1000x too large or small.
triggers: ["number input parsed wrong decimal comma", "user typed 1,5 and got 15", "form submits wrong quantity for european users", "comma decimal parsed as thousands separator", "price input off by factor of 1000"]
permissions: ["READ"]
---

## Symptom
A user in a locale that uses a comma as the decimal separator (most of continental Europe, much of Latin America) types a quantity or price like `1,5` intending "one and a half," and the application silently interprets it as `15` (comma treated as a thousands separator, or stripped entirely) or throws a validation error rejecting a correctly-formatted number. The bug is dangerous specifically because it often doesn't error visibly -- it silently produces a wrong numeric value that's off by a factor of 10, 100, or 1000, which can mean an incorrect order quantity, an incorrect price, or an incorrect measurement being submitted and accepted without any error.

## Likely causes
1. **A number input is parsed with a hardcoded assumption about which character is the decimal separator** (`parseFloat`, or stripping all commas before parsing, assuming commas are always thousands separators) rather than parsing according to the user's actual locale convention, so a comma-decimal locale's input is misinterpreted.
2. **The input is a plain `<input type="text">` styled to look numeric, parsed with generic string-to-number logic**, instead of a locale-aware numeric input component or a parser that uses `Intl.NumberFormat`'s locale data to know which separator convention applies.
3. **Client-side parsing and server-side parsing disagree** -- the frontend correctly interprets the locale's separator convention and sends a normalized value, but the API or backend independently re-parses a raw string with a different (often hardcoded US-convention) assumption, corrupting the value after it already passed client-side validation.
4. **Copy-paste or autofill from a locale-formatted source** (a spreadsheet, another app, an address bar) inserts a fully locale-formatted number including thousands separators (e.g. `1.234,56`) into a field that only expects a bare decimal number, and the parser handles the decimal separator but not the grouping separator, or vice versa.

## Diagnose
- Reproduce with a test value that's ambiguous or wrong under the incorrect interpretation for the affected locale -- typing `1,5` in a comma-decimal locale and checking whether the stored/submitted value is `1.5` or `15` immediately reveals the bug.
- Check whether the input field is a native locale-aware numeric control (some platforms provide locale-respecting numeric keyboards/inputs) or a plain text field with custom JS/parsing logic -- custom parsing logic is where the hardcoded assumption usually lives.
- Trace the value through the full path from user keystroke to stored database value: check the value at the moment of client-side parse, at the moment it's serialized for the API request, and at the moment the server parses it -- a mismatch between any two of these points identifies exactly which layer has the wrong assumption.
- Check server-side validation/parsing code independently of the client, since a client-side fix using `Intl.NumberFormat` doesn't help if the server re-parses the raw string with its own separate, potentially hardcoded logic.

## Fix
Parse locale-formatted numeric input using the locale's actual grouping/decimal conventions rather than a hardcoded assumption -- use `Intl.NumberFormat`'s parsing utilities (or a library built on them) to determine, per the active locale, which character is the decimal separator and which is the grouping separator, and normalize the value to an unambiguous internal representation (a plain numeric type, or an explicit US/ISO-style string with a period decimal) immediately at the input boundary, before it's transmitted or stored anywhere else in the system. Ensure the normalized, unambiguous value -- not the raw locale-formatted string -- is what crosses the network to the server, so server-side parsing never needs to guess a separator convention at all; if the server must also accept raw formatted input directly (e.g. a CSV import), it needs the same explicit locale-aware parsing, not a second independent hardcoded assumption.

## Pitfalls
- Fixing the frontend's parsing to be locale-aware while leaving the backend API's independent validation/parsing logic with its original hardcoded assumption still corrupts values submitted through any path that bypasses the fixed frontend (a direct API call, a bulk import, a partner integration).
- Stripping all non-digit characters before parsing "to be safe" silently discards the very information (which character was the decimal point) needed to parse the number correctly, converting an ambiguous-but-recoverable problem into an unrecoverable one.
- Normalizing to a fixed display format too early (before the user has finished typing) can fight the user's input as they type a decimal value, so the locale-aware parsing/normalization should happen on submit/blur, not on every keystroke, to avoid corrupting a partially-typed number.

## Verify
Enter a numeric value using the decimal and thousands-separator convention of a comma-decimal locale (e.g. type `1.234,56` intending one thousand two hundred thirty-four and fifty-six hundredths) and confirm the value stored server-side and any value redisplayed to the user both represent the same intended magnitude -- then repeat with a period-decimal locale's convention (`1,234.56`) and confirm both produce numerically correct, matching results end-to-end through the actual API boundary, not just in client-side unit tests.
