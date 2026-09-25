---
name: xss-prevention
description: Diagnose and fix cross-site scripting (reflected, stored, DOM-based) from unescaped user content rendered as HTML/JS.
triggers: ["xss", "cross site scripting", "script injection", "dangerouslysetinnerhtml", "innerhtml user input", "unescaped output"]
permissions: ["READ"]
---

## Symptom
Attacker-controlled content (a comment, a profile field, a URL parameter)
executes as JavaScript in another user's browser -- a script tag runs, a
cookie gets exfiltrated, or a payload persists and fires for every
subsequent visitor (stored XSS) instead of just the one request
(reflected XSS).

## Likely causes
1. **User content rendered into HTML without escaping** -- a template
   engine's "raw"/"unescaped" output mode used on attacker-influenced
   data, or hand-built HTML string concatenation.
2. **`innerHTML`/`dangerouslySetInnerHTML`/`v-html`-style APIs** given
   user content directly, bypassing the framework's default auto-
   escaping (most modern frameworks escape by default in normal
   templating -- these are the explicit escape hatches that turn it off).
3. **User content reflected into a URL, attribute, or JavaScript context**
   where HTML-escaping alone isn't sufficient (e.g. inside a `<script>`
   block, inside an `href="javascript:..."`, inside an unquoted HTML
   attribute) -- each context needs its own correct encoding, not one
   generic "escape HTML" pass.
4. **Stored content that was safe when written but becomes unsafe due to
   a later change** -- e.g. a field that used to only ever be rendered as
   plain text starts being rendered as HTML somewhere new, without
   re-auditing whether its stored content is actually safe to do so.

## Diagnose
- Identify the exact rendering context: page HTML body, an HTML
  attribute, inside a `<script>` block, or a URL -- the correct encoding
  differs per context, so this determines the fix, not just "escape it."
- Check whether the template engine's default auto-escaping was
  explicitly bypassed (a "raw"/"safe"/`html.escape=False`-style marker),
  and whether that bypass is actually necessary for that specific field.
- For DOM-based XSS specifically, trace client-side JavaScript that reads
  from `location`, `document.referrer`, or a URL fragment and writes it
  into the DOM via an unsafe sink (`innerHTML`, `eval`, etc.).
- For stored XSS, check every place the field is rendered, not just where
  it's written -- a field safe in one rendering context can be unsafe in
  another added later.

## Fix
- Rely on the template engine's default auto-escaping for HTML body
  content, and only use raw/unescaped output for content that's
  genuinely pre-sanitized HTML (e.g. output of a dedicated HTML sanitizer
  library), never for arbitrary user input.
- Use context-appropriate encoding: HTML-entity encoding for body
  content, attribute encoding for attribute values, JavaScript-string
  encoding for content embedded in a `<script>` block (and prefer not
  embedding user data directly in script blocks at all -- pass it via a
  data attribute or a JSON blob read by JS instead).
- For content that genuinely needs to allow some HTML (rich text, markdown
  rendering), use an allowlist-based HTML sanitizer library, never a
  blocklist, and sanitize on render (or at minimum on both write and
  render), not just once.
- Add a Content Security Policy as defense-in-depth (restricting inline
  script execution) so a missed escaping bug is less likely to be
  exploitable even if it exists -- not a replacement for fixing the
  escaping itself.

## Pitfalls
- Escaping on write but not on render (or vice versa) leaves a gap if
  the data is ever read and rendered through a different path that
  skips the same escaping step -- prefer escaping at render time, close
  to the actual output context, as the authoritative point.
- A generic "strip HTML tags" filter is routinely bypassable (obfuscated
  tags, attribute-based payloads like `onerror=`) -- use a maintained
  sanitizer library, not a hand-rolled regex.
- Adding a CSP without `unsafe-inline` removed doesn't actually block
  inline-script-based XSS -- verify the policy is actually restrictive,
  not just present.

## Verify
Submit a standard XSS probe payload (e.g. `<script>alert(1)</script>` or
context-appropriate variants for attribute/JS contexts) through the
previously-vulnerable field and confirm it renders as inert text/is
rejected, in every context where that field is displayed, not just the
one originally reported.
