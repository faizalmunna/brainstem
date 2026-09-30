import pytest

from brainstem.manifest import BrainManifest, ProjectConfig, VerifyConfig, load_manifest, save_manifest


def test_manifest_round_trips_quoted_values_without_toml_injection(tmp_path):
    manifest = BrainManifest(
        project=ProjectConfig(name='project "one"\n[unexpected]'),
        verify=VerifyConfig(
            commands=['python -c "print(\'quoted\')"'],
            runner="docker",
            docker_image="registry.example/verify@sha256:" + "a" * 64,
        ),
    )

    save_manifest(tmp_path, manifest)

    assert load_manifest(tmp_path) == manifest
    content = (tmp_path / ".brain" / "brain.toml").read_text(encoding="utf-8")
    assert "\n[unexpected]" not in content


def test_manifest_refuses_a_brain_state_symlink_outside_the_repository(tmp_path):
    outside = tmp_path.parent / f"outside-brain-state-{tmp_path.name}"
    outside.mkdir(exist_ok=True)
    try:
        (tmp_path / ".brain").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this test host")

    with pytest.raises(ValueError, match="outside repository"):
        save_manifest(tmp_path, BrainManifest(project=ProjectConfig(name="safe")))

    assert not (outside / "brain.toml").exists()
