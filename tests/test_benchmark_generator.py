import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("benchmark_generator", ROOT / "tools" / "generate_benchmark_corpus.py")
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def test_benchmark_generator_is_multilanguage_and_refuses_nonempty_output(tmp_path):
    output = tmp_path / "fixture"
    generator.generate(output, 8)

    assert (output / "go.mod").is_file()
    assert len(list(output.rglob("*.*"))) >= 9
    with pytest.raises(ValueError, match="non-empty"):
        generator.generate(output, 8)
