"""Keep public README inventory claims aligned with the shipped implementation."""

from __future__ import annotations

import re
from pathlib import Path

from brainstem.hosts import HOSTS
from brainstem.skills.registry import SkillRegistry
from brainstem.workspace import _bundled_skills_dir


ROOT = Path(__file__).resolve().parents[1]
HERO_GIF = ROOT / "assets" / "brainstem-agent-flow.gif"


def _mcp_tool_count() -> int:
    source = (ROOT / "src" / "brainstem" / "mcp_server.py").read_text(encoding="utf-8")
    return len(re.findall(r"@mcp\.tool\(\)", source))


def test_readme_facts_match_the_shipped_catalog_and_tool_surface() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    registry = SkillRegistry([_bundled_skills_dir()])
    expected = {
        "mcp_tools": _mcp_tool_count(),
        "bundled_skills": len(registry.list()),
        "skill_packs": len(registry.list_packs()),
        "hosts": len(HOSTS),
    }

    marker = re.search(r"<!-- brainstem-readme-facts: ([^>]+) -->", readme)
    assert marker, "README must retain its machine-checked facts marker"
    for name, value in expected.items():
        assert f"{name}={value}" in marker.group(1)

    host_marker = re.search(r"<!-- brainstem-readme-hosts: ([^>]+) -->", readme)
    assert host_marker, "README must retain its machine-checked host marker"
    assert host_marker.group(1).split(",") == list(HOSTS)
    for pack in registry.list_packs():
        assert f"<code>{pack}</code>" in readme

    # Benchmark copy must remain specific about what was measured, rather than
    # drifting into a universal token- or cost-saving marketing claim.
    for expected_text in (
        "60,114 → 2,272",
        "96.2%",
        "Recall@5 0.95",
        "10 labelled questions",
        "not a universal claim",
    ):
        assert expected_text in readme


def test_readme_animation_is_a_compact_local_guidance_asset() -> None:
    asset = HERO_GIF.read_bytes()

    assert asset.startswith((b"GIF87a", b"GIF89a"))
    assert len(asset) < 700_000
    # Each rendered scene has its own graphic-control extension. Requiring
    # three keeps the hero as a useful mini-guide, not a static image renamed
    # as a GIF.
    assert asset.count(b"\x21\xf9\x04") >= 3

