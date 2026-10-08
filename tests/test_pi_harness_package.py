import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pi_harness_package_is_a_dependency_free_skill_package():
    package = json.loads((ROOT / "integrations" / "pi" / "package.json").read_text(encoding="utf-8"))

    assert package["private"] is True
    assert "pi-package" in package["keywords"]
    assert package["pi"] == {"skills": ["./skills"]}
    assert "dependencies" not in package


def test_pi_brainstem_skill_uses_evidence_and_never_embeds_credentials():
    skill = (ROOT / "integrations" / "pi" / "skills" / "brainstem" / "SKILL.md").read_text(encoding="utf-8")

    assert "brainstem prepare" in skill
    assert "brainstem workflow start" in skill
    assert "not proof" in skill
    assert "Never put API keys" in skill
