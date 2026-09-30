from brainstem.agents.factory import infer_permissions, propose_profile, slugify
from brainstem.agents.permissions import Permission


def test_read_is_always_granted():
    granted, _ = infer_permissions("just look around and summarize the repo")
    assert Permission.READ in granted
    assert granted == {Permission.READ}


def test_write_and_execute_keywords_are_detected():
    granted, rationale = infer_permissions("Implement the new feature and run the tests to verify it")
    assert Permission.WRITE in granted
    assert Permission.EXECUTE in granted
    assert "implement" in rationale["WRITE"]
    assert "run" in rationale["EXECUTE"]
    assert "test" in rationale["EXECUTE"]


def test_deploy_and_delete_are_not_granted_unless_mentioned():
    granted, _ = infer_permissions("Write some documentation")
    assert Permission.DEPLOY not in granted
    assert Permission.DELETE not in granted
    assert Permission.WRITE in granted


def test_multiword_phrase_keyword_matches():
    granted, rationale = infer_permissions("Clean up temp files and rotate the api key")
    assert Permission.DELETE in granted
    assert Permission.SECRET in granted
    assert "clean up" in rationale["DELETE"]
    assert "api key" in rationale["SECRET"]


def test_inference_is_deterministic():
    a, _ = infer_permissions("Deploy the release to production")
    b, _ = infer_permissions("Deploy the release to production")
    assert a == b


def test_slugify_derives_a_name_from_the_description():
    assert slugify("Fix the login bug in the auth module") == "fix-the-login-bug"


def test_slugify_falls_back_when_no_words():
    assert slugify("!!!") == "agent"


def test_propose_profile_uses_slug_when_no_name_given():
    proposal = propose_profile("Deploy the app to production")
    assert proposal.name == "deploy-the-app-to"
    assert Permission.DEPLOY in proposal.permissions


def test_propose_profile_uses_explicit_name():
    proposal = propose_profile("Deploy the app to production", name="deployer")
    assert proposal.name == "deployer"


def test_propose_profile_matches_skills_from_registry():
    class FakeSkill:
        def __init__(self, name):
            self.name = name

    class FakeRegistry:
        def find_by_trigger(self, text):
            return [FakeSkill("react-hydration-mismatch")] if "react" in text.lower() else []

    proposal = propose_profile("Fix a react hydration bug", registry=FakeRegistry())
    assert proposal.matched_skills == ["react-hydration-mismatch"]


def test_propose_profile_without_registry_has_no_matched_skills():
    proposal = propose_profile("Fix a react hydration bug")
    assert proposal.matched_skills == []
