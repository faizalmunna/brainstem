---
name: insecure-deserialization
description: Diagnose remote-code-execution risk from deserializing untrusted data with an unsafe format/library (pickle, unsafe YAML load, PHP unserialize, Java ObjectInputStream).
triggers: ["insecure deserialization", "pickle load untrusted", "yaml.load unsafe", "remote code execution deserialize", "unserialize vulnerability"]
permissions: ["READ"]
---

## Symptom
Data from an untrusted source (a user upload, an API request body, a
message queue payload, a cookie) is deserialized using a format/library
that can execute arbitrary code as part of reconstructing the object --
not just parse data, but potentially run code chosen by whoever crafted
the input.

## Likely causes
1. **Python `pickle.load`/`pickle.loads` on untrusted input** -- pickle is
   explicitly documented as unsafe to unpickle data from untrusted
   sources, since it can invoke arbitrary constructors/`__reduce__`
   methods during deserialization.
2. **`yaml.load()` without a safe loader** (PyYAML's default loader
   historically supported constructing arbitrary Python objects) instead
   of `yaml.safe_load()`.
3. **Java's `ObjectInputStream.readObject()` on untrusted byte streams**,
   or equivalent unsafe deserialization in other languages (PHP's
   `unserialize()` on user input, .NET's `BinaryFormatter`) -- each has a
   well-documented history of exploitation via "gadget chains" in
   commonly-present classes on the classpath.
4. **A caching layer or session store that deserializes stored objects**,
   where the storage backend itself becomes untrusted if an attacker can
   write to it (e.g. a shared Redis instance, a poorly-secured cache).

## Diagnose
- Grep for the unsafe deserialization calls in the language/framework in
  use (`pickle.load`/`loads`, `yaml.load` without `Loader=SafeLoader`,
  `ObjectInputStream`, `unserialize`, `BinaryFormatter`) and trace each
  call's input back to its source -- is it ever attacker-influenced,
  directly or indirectly (via a queue, a cache, an upload)?
- For session/cookie-based deserialization specifically, check whether
  session data is signed/encrypted in a way that prevents tampering, or
  whether an attacker who can forge a cookie can also control its
  deserialized content.
- Check third-party libraries transitively used for the same unsafe
  patterns, not just first-party code.

## Fix
- Replace unsafe deserialization with a safe, data-only format for
  anything touching untrusted input: JSON, or a safe-mode
  loader/parser that can't construct arbitrary objects (`yaml.safe_load`,
  a schema-validated deserializer).
- If a binary/object serialization format is genuinely required, use one
  designed for this with an explicit allowlist of deserializable types
  (many modern serialization libraries support this), never unrestricted
  arbitrary-object deserialization.
- For session/cache stores, ensure the storage backend itself isn't
  writable by untrusted parties, and sign/encrypt serialized session data
  so tampering is detectable even if the store itself is compromised.
- If pickle (or an equivalent) must be used for genuinely trusted,
  internal-only data (e.g. between your own services on a private
  network with no external input path), document and enforce that trust
  boundary explicitly rather than assuming it by default.

## Pitfalls
- Switching formats but leaving the trust boundary undocumented means a
  future change (routing external input through a previously "internal-
  only" path) can silently reintroduce the vulnerability -- the actual
  fix is establishing and enforcing the trust boundary, not just the
  format choice at one point in time.
- "We control both ends so it's safe" stops being true the moment either
  end can be influenced by external input indirectly (a message queue
  fed by a public-facing service, a cache populated from user data) --
  re-verify the trust assumption whenever the data flow changes.

## Verify
Confirm the fixed code path rejects or safely ignores a crafted payload
designed to exploit the previous deserialization method (a standard
pickle/YAML exploit payload for the language in use) rather than
executing any part of it.
