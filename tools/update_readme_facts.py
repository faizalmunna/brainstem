"""Synchronize the machine-checked inventory markers at the top of README.md.

Run with ``--check`` in CI, or without it to rewrite only the two markers.
The script never rewrites README prose or presentation content.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brainstem.hosts import HOSTS  # noqa: E402
from brainstem.skills.registry import SkillRegistry  # noqa: E402
from brainstem.workspace import _bundled_skills_dir  # noqa: E402


def facts() -> dict[str, int]:
    registry = SkillRegistry([_bundled_skills_dir()])
    source = (ROOT / "src" / "brainstem" / "mcp_server.py").read_text(encoding="utf-8")
    return {
        "mcp_tools": len(re.findall(r"@mcp\.tool\(\)", source)),
        "bundled_skills": len(registry.list()),
        "skill_packs": len(registry.list_packs()),
        "hosts": len(HOSTS),
    }


def synchronized_readme(readme: str) -> str:
    inventory = facts()
    facts_marker = "<!-- brainstem-readme-facts: " + "; ".join(f"{key}={value}" for key, value in inventory.items()) + " -->"
    hosts_marker = "<!-- brainstem-readme-hosts: " + ",".join(HOSTS) + " -->"
    updated, facts_count = re.subn(r"<!-- brainstem-readme-facts: [^>]+ -->", facts_marker, readme, count=1)
    updated, hosts_count = re.subn(r"<!-- brainstem-readme-hosts: [^>]+ -->", hosts_marker, updated, count=1)
    if facts_count != 1 or hosts_count != 1:
        raise ValueError("README is missing a required brainstem-readme marker")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail instead of writing when markers are stale")
    arguments = parser.parse_args()
    path = ROOT / "README.md"
    current = path.read_text(encoding="utf-8")
    updated = synchronized_readme(current)
    if arguments.check:
        if updated != current:
            raise SystemExit("README inventory markers are stale; run: uv run python tools/update_readme_facts.py")
        return
    path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
