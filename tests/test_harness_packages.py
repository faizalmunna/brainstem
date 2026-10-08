import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "brainstem"


def _json(relative_path: str) -> dict:
    return json.loads((PLUGIN_ROOT / relative_path).read_text(encoding="utf-8"))


def _package_path(value: str) -> Path:
    """Resolve a manifest path while rejecting traversal outside the package."""
    assert value.startswith("./")
    assert ".." not in Path(value).parts
    candidate = (PLUGIN_ROOT / value).resolve()
    assert candidate.is_relative_to(PLUGIN_ROOT.resolve())
    return candidate


def test_portable_plugin_has_a_real_setup_skill_and_openai_extension():
    manifest = _json("plugin.json")

    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert manifest["name"] == "brainstem"
    extension = manifest["extensions"]["com.openai"]
    onboarding = _package_path(extension["onboardingSkill"])
    assert onboarding == PLUGIN_ROOT / "skills" / "setup" / "SKILL.md"
    assert onboarding.is_file()
    assert extension["interface"]["displayName"] == "Brainstem"
    assert extension["interface"]["defaultPrompt"]


def test_codex_compatibility_manifest_only_points_inside_plugin_and_has_onboarding():
    manifest = _json(".codex-plugin/plugin.json")

    assert manifest["name"] == "brainstem"
    assert _package_path(manifest["skills"]) == PLUGIN_ROOT / "skills"
    assert _package_path(manifest["extensions"]["com.openai"]["onboardingSkill"]).is_file()
    assert manifest["interface"]["defaultPrompt"]
    assert "mcpServers" not in manifest
    assert "hooks" not in manifest


def test_claude_cursor_and_kimi_descriptors_reuse_the_same_skill_bundle_without_hooks():
    claude = _json(".claude-plugin/plugin.json")
    cursor = _json(".cursor-plugin/plugin.json")
    kimi = _json(".kimi-plugin/plugin.json")

    assert claude["name"] == cursor["name"] == kimi["name"] == "brainstem"
    assert _package_path(cursor["skills"]) == PLUGIN_ROOT / "skills"
    assert _package_path(kimi["skills"]) == PLUGIN_ROOT / "skills"
    assert kimi["sessionStart"] == {"skill": "setup"}
    for manifest in (claude, cursor, kimi):
        assert "hooks" not in manifest
        assert "mcpServers" not in manifest


def test_repo_marketplace_exposes_the_tracked_plugin_directory():
    marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    entry = marketplace["plugins"][0]

    assert entry["name"] == "brainstem"
    assert entry["source"] == {"source": "local", "path": "./plugins/brainstem"}
    assert (ROOT / entry["source"]["path"][2:]).resolve() == PLUGIN_ROOT.resolve()


def test_setup_skill_is_honest_about_the_connection_and_credentials():
    setup = (PLUGIN_ROOT / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")

    assert "does not silently add a server" in setup
    assert "Never put API keys" in setup
    assert "not claim that Brainstem indexed" in setup
