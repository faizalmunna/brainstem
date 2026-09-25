"""Deterministic CycloneDX-style SBOM generation from the reviewed uv lockfile.

The generator intentionally uses only the default runtime graph unless an
extra is explicitly requested. Development, provider, and vector dependencies
are therefore never represented as installed production runtime dependencies
by accident.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import quote


def _load_toml(path: Path) -> dict:
    with path.open("rb") as file:
        data = tomllib.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected TOML mapping in {path}")
    return data


def _component_ref(package: dict) -> str:
    name, version = package["name"], package["version"]
    base = f"pkg:pypi/{quote(name.lower(), safe='')}@{quote(version, safe='')}"
    markers = package.get("resolution-markers", [])
    if not isinstance(markers, list) or not markers:
        return base
    marker_text = " || ".join(marker for marker in markers if isinstance(marker, str))
    marker_hash = hashlib.sha256(marker_text.encode("utf-8")).hexdigest()[:16]
    # A lock can select different versions by platform/Python. A qualifier
    # makes each resolved variant independently addressable in the BOM while
    # retaining its ordinary PyPI package URL.
    return f"{base}?uv_marker={marker_hash}"


def _sha256_from_lock(package: dict) -> str | None:
    source = package.get("sdist")
    if isinstance(source, dict) and isinstance(source.get("hash"), str):
        value = source["hash"]
        if value.startswith("sha256:"):
            return value.removeprefix("sha256:")
    wheels = package.get("wheels")
    if isinstance(wheels, list):
        for wheel in wheels:
            if isinstance(wheel, dict) and isinstance(wheel.get("hash"), str) and wheel["hash"].startswith("sha256:"):
                return wheel["hash"].removeprefix("sha256:")
    return None


def _package_index(packages: object) -> dict[str, list[dict]]:
    if not isinstance(packages, list):
        raise ValueError("uv.lock does not contain a package list")
    index: dict[str, list[dict]] = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("name"), str):
            continue
        name = package["name"].lower()
        index.setdefault(name, []).append(package)
    return index


def _dependency_names(package: dict) -> list[str]:
    dependencies = package.get("dependencies", [])
    if not isinstance(dependencies, list):
        return []
    return [dependency["name"].lower() for dependency in dependencies if isinstance(dependency, dict) and isinstance(dependency.get("name"), str)]


def generate_sbom(repo_root: Path, extras: tuple[str, ...] = ()) -> dict:
    """Return a stable BOM for default runtime dependencies plus selected extras."""
    root = repo_root.resolve()
    pyproject = _load_toml(root / "pyproject.toml")
    lock_path = root / "uv.lock"
    lock = _load_toml(lock_path)
    project = pyproject.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("name"), str) or not isinstance(project.get("version"), str):
        raise ValueError("pyproject.toml needs [project] name and version")
    index = _package_index(lock.get("package"))
    root_candidates = index.get(project["name"].lower(), [])
    if len(root_candidates) != 1:
        raise ValueError(f"uv.lock has no package entry for {project['name']}")
    root_package = root_candidates[0]

    optional = root_package.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        optional = {}
    unknown = sorted(set(extras) - set(optional))
    if unknown:
        raise ValueError(f"Unknown uv.lock extra(s): {', '.join(unknown)}")

    pending = deque(_dependency_names(root_package))
    for extra in sorted(set(extras)):
        dependencies = optional[extra]
        if isinstance(dependencies, list):
            pending.extend(
                dependency["name"].lower()
                for dependency in dependencies
                if isinstance(dependency, dict) and isinstance(dependency.get("name"), str)
            )

    selected: dict[str, dict] = {}
    while pending:
        name = pending.popleft()
        variants = index.get(name)
        if not variants:
            raise ValueError(f"uv.lock dependency {name} has no resolved package entry")
        for package in variants:
            ref = _component_ref(package)
            if ref in selected:
                continue
            selected[ref] = package
            pending.extend(_dependency_names(package))

    components = []
    dependencies = []
    for ref in sorted(selected):
        package = selected[ref]
        version = package.get("version")
        if not isinstance(version, str):
            raise ValueError(f"uv.lock package {name} has no version")
        component = {
            "type": "library",
            "name": package["name"],
            "version": version,
            "bom-ref": ref,
            "purl": ref,
        }
        digest = _sha256_from_lock(package)
        if digest:
            component["hashes"] = [{"alg": "SHA-256", "content": digest}]
        markers = package.get("resolution-markers", [])
        if isinstance(markers, list) and markers:
            component["properties"] = [
                {"name": "brainstem:uv-resolution-markers", "value": " || ".join(marker for marker in markers if isinstance(marker, str))}
            ]
        components.append(component)
        dependencies.append(
            {
                "ref": component["bom-ref"],
                "dependsOn": sorted(
                    variant_ref
                    for dependency in _dependency_names(package)
                    for variant_ref, variant in selected.items()
                    if variant["name"].lower() == dependency
                ),
            }
        )

    lock_hash = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    root_ref = f"pkg:pypi/{quote(project['name'].lower(), safe='')}@{quote(project['version'], safe='')}"
    root_dependencies = sorted(component["bom-ref"] for component in components)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, f'{root_ref}:{lock_hash}')}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": project["name"],
                "version": project["version"],
                "bom-ref": root_ref,
                "purl": root_ref,
            },
            "properties": [
                {"name": "brainstem:uv-lock-sha256", "value": lock_hash},
                {"name": "brainstem:requested-extras", "value": ",".join(sorted(set(extras)))},
            ],
        },
        "components": components,
        "dependencies": [{"ref": root_ref, "dependsOn": root_dependencies}, *dependencies],
    }


def write_sbom(repo_root: Path, output: Path, extras: tuple[str, ...] = ()) -> Path:
    """Generate and write a canonical JSON SBOM; the caller chooses its path."""
    target = output if output.is_absolute() else repo_root.resolve() / output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(generate_sbom(repo_root, extras), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
