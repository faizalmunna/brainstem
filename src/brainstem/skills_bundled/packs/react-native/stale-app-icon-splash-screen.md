---
name: stale-app-icon-splash-screen
description: Fix an app icon or splash screen that keeps showing the old image after updating the asset and rebuilding the app.
triggers: ["app icon not updating", "splash screen still shows old image", "changed app icon but rebuild shows old one", "launch screen stuck on old logo", "icon cache not clearing react native"]
permissions: ["READ"]
---

## Symptom
The app icon asset or splash screen image was replaced in the project,
the build was re-run, and the app installs successfully -- but the device
still shows the previous icon on the home screen, or the old splash image
flashes on launch, even though the source files were definitely changed
and the JS bundle reflects other changes fine.

## Likely causes
1. **The app wasn't actually reinstalled, only reloaded** -- a JS-level
   reload (Fast Refresh, "Reload" from the dev menu) never touches native
   resources like the icon or launch screen, which are baked into the
   native binary at build/install time, not read from the JS bundle.
2. **The OS itself caching the launcher icon** -- both iOS and Android
   home screens can cache app icons/launcher metadata independently of
   the installed binary, especially after an in-place reinstall over an
   existing app rather than a full uninstall.
3. **Multiple duplicate icon/splash asset locations, only some updated**
   -- iOS needs the icon set updated inside `Images.xcassets` (or wherever
   `react-native-bootsplash`/Expo's config points), and Android needs
   every density bucket (`mipmap-mdpi`, `-hdpi`, `-xhdpi`, etc.) updated;
   changing only the source asset referenced by a config tool without
   regenerating the actual native resource files leaves stale copies in
   place.
4. **A build tool caching generated native assets** -- Xcode's derived
   data, Android's Gradle build cache, or an Expo prebuild cache can keep
   serving a previously-generated icon/splash resource even after the
   source config changes, if the cache key doesn't account for the asset
   change.
5. **For Expo-managed projects, `app.json`/`app.config.js` icon/splash
   paths updated but `expo prebuild` never re-run**, so the native
   projects (`ios/`, `android/`) still contain the old generated assets
   from the last prebuild.

## Diagnose
- Confirm this is a native-asset issue, not a JS issue, by checking
  whether *any* native-level change (not just JS) has taken effect since
  the icon change -- if native changes generally aren't applying either,
  the build isn't actually running a fresh native compile.
- For iOS, inspect `ios/<App>/Images.xcassets/AppIcon.appiconset` directly
  and confirm the actual PNG files were replaced (open them, don't trust
  filenames) and that `Contents.json` references the right files.
- For Android, check every `android/app/src/main/res/mipmap-*/ic_launcher*.png`
  (and `-v26` adaptive icon variants if present) -- a common bug is
  updating only `mipmap-xxxhdpi` and assuming other densities inherit it.
- For Expo, run `expo config --type introspect` (or check
  `app.json`) to confirm the icon/splash path points where expected, then
  check whether `ios/`/`android/` exist as committed folders (meaning
  prebuild must be re-run manually) or are gitignored (meaning
  `expo prebuild`/a fresh `expo run:ios`/`run:android` regenerates them).

## Fix
- Fully uninstall the app from the device/simulator before reinstalling
  -- both platforms are known to cache launcher icon bitmaps tied to the
  existing app installation; a plain rebuild-and-reinstall over the
  existing app is not always sufficient.
- Regenerate *all* required resolutions, not just one, using the
  platform's asset catalog tooling (Xcode's asset catalog, Android
  Studio's Image Asset Studio, or `expo-splash-screen`'s generation
  command) rather than manually copying a single PNG into one folder.
- Clear the relevant native build cache: `cd ios && rm -rf
  build ~/Library/Developer/Xcode/DerivedData/<App>-*` for iOS, and
  `cd android && ./gradlew clean` for Android, before rebuilding.
- For Expo projects with gitignored native folders, run `expo prebuild
  --clean` after changing `app.json`'s icon/splash config so the native
  projects are regenerated from the updated config rather than reusing a
  stale prebuild output.

## Pitfalls
- Assuming a `expo start -c` (clearing the Metro cache) fixes an icon/
  splash issue -- Metro cache only affects the JS bundle, never native
  resources, so this wastes a debugging cycle without addressing the
  actual cache layer involved.
- Regenerating only the primary/largest icon size and leaving smaller
  density buckets stale produces a device-dependent bug (looks fixed on
  a high-density test device, still stale on others) that's easy to
  mistake for "fixed" if only tested on one device.

## Verify
Fully uninstall the app from the test device/simulator, run a completely
fresh build and install, and confirm the new icon appears on the home
screen and the new splash image appears on cold launch -- on both a
high-density and a lower-density device/emulator if Android is in scope.
