import pytest

from brainstem.agents.profile import AgentProfile, Permission, save_profile
from brainstem.agents.team import AgentTeam, TeamMember, list_teams, load_team, remove_team, save_team


def _make_profile(repo_root, name, permissions=None):
    save_profile(
        repo_root,
        AgentProfile(name=name, permissions=set(permissions or {Permission.READ})),
    )


def test_save_and_load_team(tmp_path):
    _make_profile(tmp_path, "architect")
    _make_profile(tmp_path, "reviewer")
    team = AgentTeam(
        name="feature-dev",
        description="Plan then review a feature",
        members=[TeamMember(profile="architect", role="planner"), TeamMember(profile="reviewer", role="critic")],
    )

    save_team(tmp_path, team)
    loaded = load_team(tmp_path, "feature-dev")

    assert loaded.name == "feature-dev"
    assert loaded.description == "Plan then review a feature"
    assert [(m.profile, m.role) for m in loaded.members] == [("architect", "planner"), ("reviewer", "critic")]


def test_save_team_rejects_nonexistent_member_profile(tmp_path):
    team = AgentTeam(name="x", members=[TeamMember(profile="does-not-exist", role="planner")])
    with pytest.raises(FileNotFoundError):
        save_team(tmp_path, team)


def test_save_team_can_skip_validation(tmp_path):
    # Used deliberately, not the default -- confirms the validation is a
    # real, bypassable safety net, not baked unconditionally into the format.
    team = AgentTeam(name="x", members=[TeamMember(profile="does-not-exist", role="planner")])
    save_team(tmp_path, team, validate_profiles=False)
    loaded = load_team(tmp_path, "x")
    assert loaded.members[0].profile == "does-not-exist"


def test_list_teams(tmp_path):
    _make_profile(tmp_path, "a")
    save_team(tmp_path, AgentTeam(name="team-one", members=[TeamMember(profile="a", role="x")]))
    save_team(tmp_path, AgentTeam(name="team-two", members=[TeamMember(profile="a", role="y")]))

    assert list_teams(tmp_path) == ["team-one", "team-two"]


def test_list_teams_empty_when_none_created(tmp_path):
    assert list_teams(tmp_path) == []


def test_load_missing_team_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_team(tmp_path, "nonexistent")


def test_remove_team(tmp_path):
    _make_profile(tmp_path, "a")
    save_team(tmp_path, AgentTeam(name="temp-team", members=[TeamMember(profile="a", role="x")]))

    remove_team(tmp_path, "temp-team")

    assert list_teams(tmp_path) == []


def test_remove_nonexistent_team_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        remove_team(tmp_path, "nonexistent")


@pytest.mark.parametrize("name", ["../escape", "a/b", "", "name with spaces"])
def test_team_name_cannot_escape_its_directory(tmp_path, name):
    with pytest.raises(ValueError):
        load_team(tmp_path, name)


def test_team_with_no_members_is_valid(tmp_path):
    # An empty team is unusual but not invalid -- e.g. a placeholder a
    # user is about to fill in. Shouldn't be a special error case.
    save_team(tmp_path, AgentTeam(name="empty-team"))
    loaded = load_team(tmp_path, "empty-team")
    assert loaded.members == []
