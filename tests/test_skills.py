from pathlib import Path

import pytest

from brainstem.skills.manager import install_pack, list_installed_packs, remove_pack
from brainstem.skills.registry import GENERAL_PACK, SkillRegistry
from brainstem.skills.state import SkillState


def _write_skill(path: Path, name: str, triggers: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    triggers_yaml = f"triggers: {triggers!r}".replace("'", '"') if triggers else "triggers: []"
    path.write_text(
        f"---\nname: {name}\ndescription: test skill {name}\n{triggers_yaml}\npermissions: [READ]\n---\n\nBody for {name}.\n",
        encoding="utf-8",
    )


def test_loose_skill_is_general_pack(tmp_path):
    _write_skill(tmp_path / "loose.md", "loose-skill")
    registry = SkillRegistry([tmp_path])

    skill = registry.get("loose-skill")
    assert skill is not None
    assert skill.pack == GENERAL_PACK


def test_nested_pack_skill_gets_its_pack_name(tmp_path):
    _write_skill(tmp_path / "packs" / "frontend-react" / "hydration.md", "react-hydration-mismatch")
    registry = SkillRegistry([tmp_path])

    skill = registry.get("react-hydration-mismatch")
    assert skill is not None
    assert skill.pack == "frontend-react"


def test_list_packs_and_filter_by_pack(tmp_path):
    _write_skill(tmp_path / "packs" / "frontend-react" / "a.md", "a")
    _write_skill(tmp_path / "packs" / "qa-playwright" / "b.md", "b")
    _write_skill(tmp_path / "loose.md", "c")
    registry = SkillRegistry([tmp_path])

    assert registry.list_packs() == ["frontend-react", "general", "qa-playwright"]
    assert [s.name for s in registry.list(pack="frontend-react")] == ["a"]
    assert len(registry.list()) == 3


def test_readme_files_are_not_treated_as_skills(tmp_path):
    (tmp_path / "packs" / "frontend-react").mkdir(parents=True)
    (tmp_path / "packs" / "frontend-react" / "README.md").write_text("# Not a skill\n", encoding="utf-8")
    _write_skill(tmp_path / "packs" / "frontend-react" / "real.md", "real-skill")

    registry = SkillRegistry([tmp_path])
    assert [s.name for s in registry.list()] == ["real-skill"]


def test_find_by_trigger_matches_across_packs(tmp_path):
    _write_skill(tmp_path / "packs" / "qa-playwright" / "flaky.md", "flaky-test", triggers=["flaky test", "e2e flake"])
    registry = SkillRegistry([tmp_path])

    assert [s.name for s in registry.find_by_trigger("why is this e2e flake happening again")] == ["flaky-test"]
    assert registry.find_by_trigger("unrelated question") == []


def test_installed_pack_is_discovered_and_scoped_to_its_own_pack_name(tmp_path):
    _write_skill(tmp_path / "installed" / "third-party-pack" / "x.md", "third-party-skill")
    registry = SkillRegistry([tmp_path])

    skill = registry.get("third-party-skill")
    assert skill is not None
    assert skill.pack == "third-party-pack"


# --- enable/disable state ---


def test_disabled_skill_is_hidden_from_list_but_not_get(tmp_path):
    _write_skill(tmp_path / "a.md", "a")
    state = SkillState(tmp_path / "state.json")
    state.disable("a")
    registry = SkillRegistry([tmp_path], state=state)

    assert registry.list() == []
    assert registry.list(include_disabled=True)[0].name == "a"
    assert registry.get("a") is not None  # unfiltered lookup still works
    assert registry.is_enabled("a") is False


def test_disabled_skill_is_excluded_from_trigger_matching(tmp_path):
    _write_skill(tmp_path / "a.md", "a", triggers=["some trigger phrase"])
    state = SkillState(tmp_path / "state.json")
    state.disable("a")
    registry = SkillRegistry([tmp_path], state=state)

    assert registry.find_by_trigger("some trigger phrase here") == []


def test_skill_state_persists_across_instances(tmp_path):
    path = tmp_path / "state.json"
    SkillState(path).disable("a")
    reloaded = SkillState(path)

    assert reloaded.is_enabled("a") is False
    assert reloaded.list_disabled() == ["a"]

    reloaded.enable("a")
    assert SkillState(path).is_enabled("a") is True


# --- install/remove (package manager) ---


def test_install_pack_from_local_directory(tmp_path):
    source = tmp_path / "my-custom-pack"
    _write_skill(source / "custom.md", "my-custom-skill")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    pack_name = install_pack(str(source), repo_root)

    assert pack_name == "my-custom-pack"
    assert (repo_root / ".brain" / "skills" / "installed" / "my-custom-pack" / "custom.md").exists()
    assert list_installed_packs(repo_root) == ["my-custom-pack"]


def test_install_pack_custom_name(tmp_path):
    source = tmp_path / "source-dir"
    _write_skill(source / "x.md", "x")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    pack_name = install_pack(str(source), repo_root, name="renamed-pack")

    assert pack_name == "renamed-pack"
    assert (repo_root / ".brain" / "skills" / "installed" / "renamed-pack").is_dir()


def test_install_pack_refuses_to_overwrite_existing(tmp_path):
    source = tmp_path / "source-dir"
    _write_skill(source / "x.md", "x")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    install_pack(str(source), repo_root)
    with pytest.raises(FileExistsError):
        install_pack(str(source), repo_root)


def test_install_pack_rejects_non_directory_source(tmp_path):
    not_a_dir = tmp_path / "not_here"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(NotADirectoryError):
        install_pack(str(not_a_dir), repo_root)


def test_installed_pack_is_actually_discoverable_after_install(tmp_path):
    source = tmp_path / "my-pack"
    _write_skill(source / "s.md", "installed-and-discoverable")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    install_pack(str(source), repo_root)
    registry = SkillRegistry([repo_root / ".brain" / "skills"])

    skill = registry.get("installed-and-discoverable")
    assert skill is not None
    assert skill.pack == "my-pack"


def test_remove_pack(tmp_path):
    source = tmp_path / "my-pack"
    _write_skill(source / "s.md", "s")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    install_pack(str(source), repo_root)

    remove_pack("my-pack", repo_root)

    assert list_installed_packs(repo_root) == []


def test_remove_nonexistent_pack_raises(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    with pytest.raises(FileNotFoundError):
        remove_pack("does-not-exist", repo_root)
