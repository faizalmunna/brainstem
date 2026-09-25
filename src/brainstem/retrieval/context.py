"""Bounded, path-safe source excerpts for retrieval results.

Retrieval metadata alone still makes an agent open whole files.  This module
turns ranked hits into small, line-numbered excerpts while preserving two
security invariants: every resolved path must stay inside the repository and
the total response is capped.  It deliberately has no filesystem write path.
"""

from __future__ import annotations

from pathlib import Path

from .engine import RetrievalHit

MIN_BUNDLE_CHARS = 500
MAX_BUNDLE_CHARS = 16_000
MAX_BUNDLE_HITS = 10
CONTEXT_LINES = 18
_SENSITIVE_FILENAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "secrets"}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


def _looks_sensitive(path: Path) -> bool:
    name = path.name.lower()
    return (
        (name.startswith(".env") and not name.endswith(".example"))
        or name in _SENSITIVE_FILENAMES
        or path.suffix.lower() in _SENSITIVE_SUFFIXES
    )


def build_context_bundle(
    repo_root: Path,
    hits: list[RetrievalHit],
    *,
    max_chars: int = 12_000,
    context_lines: int = CONTEXT_LINES,
) -> dict:
    """Return bounded excerpts around retrieval hits.

    Files that do not resolve within ``repo_root`` (including escaping
    symlinks), are unreadable, or contain NUL bytes are omitted.  A caller
    gets metadata for the excerpted region rather than an unbounded file.
    """
    if not MIN_BUNDLE_CHARS <= max_chars <= MAX_BUNDLE_CHARS:
        raise ValueError(f"max_chars must be between {MIN_BUNDLE_CHARS} and {MAX_BUNDLE_CHARS}")
    if not 1 <= context_lines <= 100:
        raise ValueError("context_lines must be between 1 and 100")

    root = repo_root.resolve()
    excerpts: list[dict] = []
    covered_ranges: dict[str, list[tuple[int, int]]] = {}
    remaining = max_chars
    skipped = 0
    sensitive_skipped = 0
    deduplicated = 0

    for hit in hits[:MAX_BUNDLE_HITS]:
        try:
            candidate = (root / hit.file).resolve()
            candidate.relative_to(root)
        except (OSError, ValueError):
            skipped += 1
            continue
        if not candidate.is_file():
            skipped += 1
            continue
        if _looks_sensitive(candidate):
            skipped += 1
            sensitive_skipped += 1
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped += 1
            continue
        if "\x00" in text:
            skipped += 1
            continue

        lines = text.splitlines()
        if not lines:
            continue
        center = max((hit.line or 1) - 1, 0)
        start = max(center - context_lines, 0)
        end = min(center + context_lines + 1, len(lines))
        # Multiple strong symbols often live inside the same function/class.
        # Sending their overlapping line ranges twice wastes context without
        # adding evidence. A non-overlapping distant symbol in the same file
        # is retained, because it can still be independently relevant.
        if any(start < covered_end and end > covered_start for covered_start, covered_end in covered_ranges.get(hit.file, [])):
            deduplicated += 1
            continue
        numbered = "\n".join(f"{number:>5}: {line}" for number, line in enumerate(lines[start:end], start + 1))
        if len(numbered) > remaining:
            numbered = numbered[:remaining]
        if not numbered:
            break
        excerpts.append(
            {
                "file": hit.file,
                "symbol": hit.symbol,
                "start_line": start + 1,
                "end_line": end,
                "content": numbered,
                "char_count": len(numbered),
                "truncated": len(numbered) < len("\n".join(
                    f"{number:>5}: {line}" for number, line in enumerate(lines[start:end], start + 1)
                )),
            }
        )
        covered_ranges.setdefault(hit.file, []).append((start, end))
        remaining -= len(numbered)
        if remaining == 0:
            break

    return {
        "excerpts": excerpts,
        "total_chars": max_chars - remaining,
        "truncated": remaining == 0 or skipped > 0,
        "skipped": skipped,
        "sensitive_skipped": sensitive_skipped,
        "deduplicated": deduplicated,
        "max_chars": max_chars,
    }
