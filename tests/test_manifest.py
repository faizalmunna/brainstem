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
