---
name: classloader-nosuchmethoderror-dependency-conflict
description: Diagnose a Spring Boot application that compiles fine but throws NoSuchMethodError or NoClassDefFoundError at runtime due to conflicting library versions on the classpath.
triggers: ["nosuchmethoderror spring boot", "noclassdeffounderror at runtime", "worked in ide but fails in jar", "dependency version conflict classpath", "abstractmethoderror after upgrading dependency"]
permissions: ["READ"]
---

## Symptom
The application builds successfully and the specific method being
called clearly exists in the source/API being compiled against, but at
runtime it throws `NoSuchMethodError`, `NoSuchFieldError`,
`AbstractMethodError`, or `NoClassDefFoundError` for a class or method
that "obviously exists." It frequently only appears after packaging into
the runnable jar (works fine running from the IDE), or only after adding
or upgrading one seemingly unrelated dependency, or only in one
deployment environment and not another.

## Likely causes
1. **Two different versions of the same library end up on the runtime
   classpath**, typically pulled in transitively by two different direct
   dependencies that each depend on a different version of a shared
   library -- the compiler resolved against one version's API, but at
   runtime the *other* version's class (missing the method used) is the
   one actually loaded, because build tools pick one version per
   coordinate and only one wins.
2. **A Spring Boot starter's managed version was overridden**, directly
   or transitively, by another dependency's own version constraint --
   the Spring Boot BOM (`spring-boot-dependencies`) is designed to keep
   the whole ecosystem's versions mutually compatible, and manually
   pinning one library to a version outside that matrix reintroduces the
   exact incompatibility the BOM exists to prevent.
3. **The fat/uber jar's shading or repackaging step merges conflicting
   resources incorrectly** -- e.g. two dependencies each shipping a
   `META-INF/services` file for the same SPI, and the Spring Boot
   repackage plugin (or a manual shading step) keeps only one, silently
   dropping the other's registration and causing runtime lookups to fail
   for a class that's genuinely present in the jar.
4. **A different, incompatible runtime classloader picks up a stray
   older jar** -- an application server, a shared lib directory, or an
   `EXTRA_CLASSPATH`-style environment variable injects a version that
   differs from the one bundled in the deployed artifact, so the built
   jar is correct but the deployed runtime classpath isn't what was
   tested.

## Diagnose
- Run the build tool's dependency tree and grep it for the library named
  in the error (`mvn dependency:tree | grep <artifact>` or
  `gradle dependencies | grep <artifact>`) -- if it lists the same
  artifact at more than one version pulled in via different parents,
  that's the conflict; the tool also shows which version "won" the
  resolution.
- Confirm which version actually loaded at runtime by adding a startup
  log line that prints the offending class's code source location
  (`SomeClass.class.getProtectionDomain().getCodeSource().getLocation()`)
  -- this points at the exact jar file providing the class that's
  missing the expected method.
- Decompile or `javap` that specific class from that specific jar
  (`javap -classpath the-jar.jar fully.qualified.ClassName`) and confirm
  the method really is absent from that version -- this proves version
  mismatch rather than some unrelated classloading isolation issue (e.g.
  OSGi, a custom classloader, or a plugin system loading classes twice).
- For fat-jar-specific symptoms, unzip the built jar and check
  `META-INF/services/` and any merged config files for the SPI in
  question, comparing against what each individual source dependency jar
  contains.

## Fix
Force a single, Spring-Boot-BOM-compatible version to win consistently
rather than letting transitive resolution pick arbitrarily:
- In Maven, add an explicit `<dependencyManagement>` entry (or in
  Gradle, a `resolutionStrategy.force`/platform constraint) pinning the
  conflicting artifact to one version everywhere in the dependency
  graph, preferring the version Spring Boot's own BOM already manages
  unless there's a specific documented reason to deviate.
- If a direct dependency insists on an incompatible transitive version,
  exclude that transitive dependency explicitly on the offending direct
  dependency and let the BOM-managed version supply it instead.
- For merged-SPI-file problems in a shaded/fat jar, configure the
  packaging plugin's transformer to *append/merge* same-path resource
  files (e.g. Maven Shade's `ServicesResourceTransformer`, or Spring
  Boot's own layered jar handling) instead of the default
  overwrite-on-conflict behavior.

## Pitfalls
- Deleting one of the two jar files manually from a deployment
  directory as a quick fix works until the next build regenerates the
  classpath from the dependency graph exactly as before -- always fix
  the *declared* dependency graph (pom/build file), not the artifact
  produced by it, or the fix silently reverts on the next build.
- Bumping the conflicting library to "whatever's newest" without
  checking Spring Boot's compatibility matrix can trade one
  `NoSuchMethodError` for a different one against an unrelated
  Spring-managed dependency that also transitively depends on it --
  always resolve toward the version the Spring Boot BOM for the
  in-use Boot version actually manages, not just toward newest.

## Verify
Re-run the build tool's dependency tree command and confirm the
previously-conflicting artifact now resolves to exactly one version
across the entire tree, then run the originally-failing code path
end-to-end from the packaged artifact (not the IDE) in an environment
matching production classloading (the actual runnable jar, the actual
deployment target) and confirm the error no longer occurs.
