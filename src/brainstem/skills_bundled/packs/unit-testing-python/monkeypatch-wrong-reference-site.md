---
name: monkeypatch-wrong-reference-site
description: A pytest monkeypatch or mock.patch call has no effect on the code under test because it patched the definition site instead of the module that actually imports and calls it.
triggers: ["monkeypatch not working", "mock patch has no effect", "patched function still calls real implementation", "pytest patch wrong module"]
permissions: ["READ"]
---

## Symptom

A test uses `monkeypatch.setattr()` or `unittest.mock.patch()` targeting
a function, expecting the code under test to call the patched version,
but the real, unpatched implementation still runs -- the test's
assertions about the mock (call count, return value override) fail even
though the patch call itself didn't raise any error.

## Likely causes

- **The patch targets the function's original definition module**
  (`mypackage.utils.send_email`) while the code under test imported it
  with `from mypackage.utils import send_email`, binding its own local
  name to the function object at import time -- patching the original
  module's attribute doesn't affect the already-bound local reference in
  the module under test.
- **The patch is applied after the module under test already imported
  and cached a reference** to the function, so the patch changes a
  reference nothing actually looks up again.
- **A patch target string has a typo or refers to a re-exported/aliased
  name** that doesn't match the actual import path used by the code under
  test, silently patching a different (or nonexistent, if using
  `monkeypatch.setattr` in strict mode) attribute.
- **The function is called through an instance/class attribute that was
  bound before the patch was applied** (e.g. stored as a default argument
  value or class attribute at class-definition time), so the patch
  doesn't affect an already-captured reference.

## Diagnose

1. Identify exactly how the code under test imports/references the
   target function -- `import module; module.func()` versus
   `from module import func; func()` -- since the correct patch target
   differs between these two import styles.
2. Patch at the location the code under test actually looks up the
   name from (typically `patch('module_under_test.func_name', ...)`
   rather than `patch('original_module.func_name', ...)`), and verify the
   mock's `call_count`/`assert_called` reflects the expected invocation.
3. Add a quick debug print or breakpoint inside the real (unpatched)
   implementation temporarily to confirm definitively whether it's still
   being executed despite the patch.
4. Check for any default-argument or class-attribute binding that
   captures the function reference at class/module definition time,
   before the patch has a chance to apply.

## Fix

Patch the name as it's looked up in the module under test, not where
it's originally defined -- the correct target is always "the module that
does the importing," matched to how that module imported the symbol
(`from x import y` needs patching `test_module.y`; `import x` needs
patching `x.y`). For a function reference captured at class/module
definition time (a default argument, a class attribute assigned from the
function), patch the underlying dependency it's derived from, or
restructure the code to look up the dependency at call time rather than
capture it at definition time, making it patchable.

## Pitfalls

Don't "fix" an unpatchable capture-at-definition-time pattern by making
the target function reference mutable via a workaround specific to
testing (e.g. exposing an internal test-only hook) -- prefer restructuring
the dependency to be genuinely injectable (a parameter, a class attribute
looked up fresh each call) so it's naturally testable without special-
casing. Also don't assume a patch "worked" just because it didn't raise
an error -- `monkeypatch.setattr` with `raising=True` (the default) does
verify the attribute exists, but a wrong-but-existing target won't raise
and will silently patch nothing that matters.

## Verify

Confirm the mock's assertion methods (`assert_called_once_with`, a
custom `monkeypatch`-set sentinel return value actually being returned)
succeed, and that the previously-observed real side effect (an actual
email send, a real API call) no longer occurs during the test run,
proving the patch is genuinely intercepting the call.
