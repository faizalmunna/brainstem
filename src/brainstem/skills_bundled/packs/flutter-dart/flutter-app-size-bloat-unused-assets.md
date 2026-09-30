---
name: flutter-app-size-bloat-unused-assets
description: Diagnose release app size bloat caused by unused assets or fonts that aren't tree-shaken.
triggers: ["flutter apk too large", "app size bloat flutter", "reduce flutter app size", "why is my ipa so big"]
permissions: ["READ"]
---

## Symptom
The release APK/AAB/IPA is far larger than expected (e.g. 40MB+ for a
simple app), and `flutter build apk --analyze-size` (or the equivalent
size report) attributes large chunks to fonts or assets that aren't
actually used anywhere in the shipped screens.

## Likely causes
1. **Bundling entire icon font families** (the full `MaterialIcons`/
   `CupertinoIcons` set, or a custom icon font with hundreds of glyphs)
   when the app references only a handful of icons, and font
   tree-shaking isn't taking effect for that font.
2. **Declaring whole asset directories in `pubspec.yaml`**
   (`assets: - assets/images/`) that include unused, leftover, or
   redundant resolution variants (@1x/@2x/@3x) well beyond what code
   actually references.
3. **Large uncompressed images** (PNG where WebP/JPEG would suffice), or
   multiple duplicate copies of the same asset left over from earlier
   design iterations and never cleaned up.
4. **Third-party packages bundling their own large asset/font sets**
   that ship regardless of whether the app uses that feature (e.g. a
   full icon pack pulled in for one icon).

## Diagnose
- Run `flutter build apk --analyze-size` (or the platform-appropriate
  flag) and inspect the generated size report/treemap for the largest
  contributors under `assets/` and `fonts/`.
- Cross-reference `pubspec.yaml`'s asset declarations against a grep for
  `Image.asset(...)`/`AssetImage`/font family references in the codebase
  to find files declared but never used.
- Check the build output for a font tree-shaking summary line -- icons
  referenced via non-const `IconData` construction (e.g. built from a
  dynamic code point) disable tree-shaking for that font entirely.
- Compare per-folder size (`du -sh` per asset subdirectory) or use
  DevTools' App Size tool across two builds to isolate exactly which
  files changed the total.

## Fix
- Remove unused asset files and directories, and scope `pubspec.yaml`
  asset declarations to the specific files actually referenced instead
  of whole broad folders.
- Prefer vector formats or compressed raster formats (WebP) where
  quality permits, and ship only the resolution variants actually needed
  for target devices.
- Reference icons through `const IconData(...)`/the generated icon
  class's static const fields, never built dynamically from a variable
  code point, so Flutter's font tree-shaker can statically determine
  which glyphs are used and strip the rest.
- Audit third-party dependencies for optional asset-heavy features and
  either configure them to exclude unused assets or replace them with a
  lighter alternative.

## Pitfalls
- Constructing `IconData` dynamically (e.g. from a code point stored in
  a config or database) silently disables tree-shaking for that whole
  font, quietly reintroducing the bloat later even after someone "fixed"
  it elsewhere -- keep icon references statically analyzable.
- Deleting an asset referenced only from a rarely-hit code path (e.g. an
  error-state illustration) without grepping thoroughly causes a runtime
  "unable to load asset" exception that won't surface until that path is
  actually hit in production.

## Verify
Re-run `flutter build apk --analyze-size` (or the iOS/AAB equivalent)
after cleanup and confirm both the total build size dropped and the
asset/font line items shrank proportionally to what was removed, while a
full manual pass still renders every screen correctly.
