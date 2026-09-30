"""Generate deterministic multi-language scale fixtures without committing them.

Usage:
    python tools/generate_benchmark_corpus.py --output /tmp/brainstem-100k --files 100000

The generator creates harmless structured source files. It is intentionally
outside the installed runtime and never fetches a repository or calls a model.
"""

from __future__ import annotations

import argparse
from pathlib import Path


TEMPLATES = {
    "python": ("py", "from pkg{prev}.module{prev} import value\n\ndef item{n}():\n    return value + {n}\n"),
    "typescript": ("ts", "import {{ value }} from '../pkg{prev}/module{prev}';\nexport const item{n} = () => value + {n};\n"),
    "go": ("go", "package pkg{group}\n\nfunc Item{n}() int {{ return {n} }}\n"),
    "java": ("java", "package generated.pkg{group};\npublic final class Item{n} {{ public int value() {{ return {n}; }} }}\n"),
}


def generate(output: Path, files: int) -> None:
    if files < 4:
        raise ValueError("files must be at least 4")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Refusing to populate non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    languages = list(TEMPLATES)
    for number in range(files):
        language = languages[number % len(languages)]
        extension, template = TEMPLATES[language]
        group = number // 100
        previous = max(0, number - len(languages))
        directory = output / language / f"pkg{group}"
        directory.mkdir(parents=True, exist_ok=True)
        source = template.format(n=number, group=group, prev=previous)
        (directory / f"module{number}.{extension}").write_text(source, encoding="utf-8")
    (output / "go.mod").write_text("module example.com/brainstem-benchmark\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--files", type=int, default=100_000)
    arguments = parser.parse_args()
    generate(arguments.output.resolve(), arguments.files)


if __name__ == "__main__":
    main()
