"""Automated quality gate for the real, bundled skill library -- distinct
from test_skills.py, which tests SkillRegistry's *mechanics* against
synthetic tmp_path fixtures. This tests the *content* actually shipped.

This exists specifically because of a real correctness risk at scale:
SkillRegistry's loader treats `name` as a dict key and lets a later file
silently override an earlier one with the same name (see registry.py's
own comment: "later dirs override earlier ones"). With one library grown
by hand that was a non-issue; with many packs authored in parallel batches
it's a real way to silently lose a skill. This test makes that failure
mode loud instead of silent, and enforces the same quality-bar structure
`src/brainstem/skills_bundled/packs/README.md` documents, so a
low-effort/templated skill fails tests instead of quietly shipping.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / "src" / "brainstem" / "skills_bundled"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
REQUIRED_SECTIONS = ["## Symptom", "## Likely causes", "## Diagnose", "## Fix", "## Pitfalls", "## Verify"]


def _all_skill_files() -> list[Path]:
    return [
        p
        for p in SKILLS_ROOT.rglob("*.md")
        if not p.name.upper().startswith("README")
    ]


def _parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    assert match, f"{path}: missing YAML frontmatter block"
    front_raw, body = match.groups()
    front = yaml.safe_load(front_raw) or {}
    return front, body


def test_no_duplicate_skill_names_across_the_whole_library():
    seen: dict[str, Path] = {}
    dupes: list[str] = []
    for path in _all_skill_files():
        front, _ = _parse(path)
        name = front.get("name")
        if name in seen:
            dupes.append(f"'{name}' in both {seen[name].relative_to(REPO_ROOT)} and {path.relative_to(REPO_ROOT)}")
        else:
            seen[str(name)] = path
    assert not dupes, "Duplicate skill names silently shadow each other in SkillRegistry:\n" + "\n".join(dupes)


def test_every_skill_has_required_frontmatter_fields():
    problems = []
    for path in _all_skill_files():
        front, _ = _parse(path)
        for field in ("name", "description", "triggers", "permissions"):
            if field not in front:
                problems.append(f"{path.relative_to(REPO_ROOT)}: missing '{field}'")
        if "name" in front and front["name"] != path.stem:
            problems.append(
                f"{path.relative_to(REPO_ROOT)}: frontmatter name '{front['name']}' != filename stem '{path.stem}'"
            )
        if "triggers" in front and not front["triggers"]:
            problems.append(f"{path.relative_to(REPO_ROOT)}: empty triggers list")
    assert not problems, "\n".join(problems)


def _pack_skill_files() -> list[Path]:
    """Skills under packs/<name>/ or installed/<name>/ -- the ones the
    README's quality bar actually applies to. The two original loose
    skills (repo-exploration, bug-history-check) are how-to-use-brainstem
    meta-skills, not domain-symptom skills, and predate that bar."""
    return [p for p in _all_skill_files() if "packs" in p.parts or "installed" in p.parts]


def test_every_pack_skill_follows_the_six_part_quality_bar():
    problems = []
    for path in _pack_skill_files():
        _, body = _parse(path)
        missing = [section for section in REQUIRED_SECTIONS if section not in body]
        if missing:
            problems.append(f"{path.relative_to(REPO_ROOT)}: missing section(s) {missing}")
    assert not problems, "\n".join(problems)


def test_every_pack_skill_description_is_a_specific_symptom_not_a_bare_topic():
    """A weak heuristic, not a full quality judge: catches the most obvious
    namesake-bloat smell (a one-or-two-word description) without trying to
    fully automate the judgment call the quality bar describes."""
    problems = []
    for path in _pack_skill_files():
        front, _ = _parse(path)
        description = str(front.get("description", ""))
        if len(description.split()) < 6:
            problems.append(f"{path.relative_to(REPO_ROOT)}: description too short to be a specific symptom: {description!r}")
    assert not problems, "\n".join(problems)


def test_pack_names_match_directory_convention():
    """Every skill under packs/<name>/ or installed/<name>/ must report
    that name as its pack -- catches a file placed at the wrong nesting
    depth (a common copy/paste mistake when generating many packs)."""
    from brainstem.skills.registry import SkillRegistry

    registry = SkillRegistry([SKILLS_ROOT])
    for skill in registry.list(include_disabled=True):
        path = Path(skill.source_path)
        if "packs" in path.parts:
            idx = path.parts.index("packs")
            expected_pack = path.parts[idx + 1]
            assert skill.pack == expected_pack, f"{path}: expected pack '{expected_pack}', got '{skill.pack}'"
