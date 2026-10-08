from brainstem.manifest import DEFAULT_IGNORE, default_manifest


def test_default_index_ignores_ephemeral_benchmark_output():
    assert ".tmp" in DEFAULT_IGNORE
    assert ".tmp" in default_manifest("repo").index.ignore
