"""Run a reproducible local indexing benchmark and emit JSON evidence.

Examples:
  uv run python tools/generate_benchmark_corpus.py --output .tmp/bench --files 10000
  uv run python tools/benchmark_index.py --path .tmp/bench --runs 5

No network, model, or native compiler is needed. Compare results only on the
same machine and corpus; this is an engineering measurement, not marketing.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brainstem.indexer.graph import build_graph  # noqa: E402
from brainstem.manifest import default_manifest  # noqa: E402


def run(path: Path, runs: int) -> dict[str, object]:
    if runs < 1:
        raise ValueError("runs must be at least 1")
    path = path.resolve()
    manifest = default_manifest(path.name)
    samples: list[float] = []
    last_stats: dict[str, int] = {}
    for _ in range(runs):
        started = time.perf_counter()
        graph = build_graph(path, manifest, existing=None)
        samples.append(time.perf_counter() - started)
        last_stats = graph.stats()
    return {
        "schema_version": 1,
        "repository": str(path),
        "runs": runs,
        "seconds": {"samples": samples, "min": min(samples), "median": statistics.median(samples), "max": max(samples)},
        "graph": last_stats,
        "engine": "python",
        "network": "disabled",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path, help="optional JSON evidence destination")
    arguments = parser.parse_args()
    result = run(arguments.path, arguments.runs)
    encoded = json.dumps(result, indent=2) + "\n"
    if arguments.output:
        arguments.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
