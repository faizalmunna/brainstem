import pytest

from brainstem.agents.permissions import Permission, PermissionDenied, require_permission
from brainstem.agents.profile import AgentProfile, full_access_profile, readonly_profile, save_profile, load_profile


def test_full_access_profile_grants_everything():
    profile = full_access_profile()
    for tool in ("describe_project", "record_decision", "propose_capability"):
        require_permission(tool, profile)  # should not raise


def test_readonly_profile_blocks_write_tools():
    profile = readonly_profile()
    require_permission("describe_project", profile)  # READ tool -- fine
    with pytest.raises(PermissionDenied) as exc_info:
        require_permission("record_decision", profile)  # WRITE tool -- denied
    assert exc_info.value.required == Permission.WRITE
    assert exc_info.value.tool == "record_decision"


def test_readonly_profile_blocks_workflow_writes_but_allows_workflow_reads():
    profile = readonly_profile()
    require_permission("get_workflow_state", profile)
    require_permission("get_next_work_item", profile)
    require_permission("get_context_bundle", profile)
    require_permission("prepare_task", profile)
    with pytest.raises(PermissionDenied) as exc_info:
        require_permission("start_workflow", profile)
    assert exc_info.value.required == Permission.WRITE


def test_unknown_tool_raises_keyerror():
    profile = full_access_profile()
    with pytest.raises(KeyError):
        require_permission("not_a_real_tool", profile)


def test_profile_round_trips_through_toml(tmp_path):
    profile = AgentProfile(
        name="reviewer",
        description="Read-only reviewer",
        permissions={Permission.READ},
        skills=["repo-exploration"],
    )
    save_profile(tmp_path, profile)
    loaded = load_profile(tmp_path, "reviewer")

    assert loaded.name == "reviewer"
    assert loaded.permissions == {Permission.READ}
    assert loaded.skills == ["repo-exploration"]


def test_load_missing_profile_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path, "does-not-exist")


@pytest.mark.parametrize("name", ["../escape", "a/b", "", "name with spaces"])
def test_profile_name_cannot_escape_its_directory(tmp_path, name):
    with pytest.raises(ValueError):
        load_profile(tmp_path, name)
    with pytest.raises(ValueError):
        AgentProfile(name=name)


def test_profile_toml_escapes_untrusted_description_and_skill(tmp_path):
    profile = AgentProfile(
        name="safe",
        description='line one\npermissions = ["EXECUTE"]',
        permissions={Permission.READ},
        skills=['skill"name'],
    )
    save_profile(tmp_path, profile)

    loaded = load_profile(tmp_path, "safe")

    assert loaded.permissions == {Permission.READ}
    assert loaded.description == profile.description
    assert loaded.skills == profile.skills
