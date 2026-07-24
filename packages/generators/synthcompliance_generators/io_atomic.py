"""Atomic filesystem writes — temp file then rename into place."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    if rows:
        text += "\n"
    atomic_write_text(path, text)


def write_json(path: Path, obj: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_dataset_bundle(
    out_dir: Path,
    *,
    audit_logs: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    qa_pairs: list[dict[str, Any]],
    validation_report: dict[str, Any],
    dataset_manifest: dict[str, Any] | None = None,
) -> None:
    """Write all contract files atomically (each via rename)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Write report last so UI sees consistent logs first when possible;
    # still each file is atomic individually.
    write_jsonl(out_dir / "audit_logs.jsonl", audit_logs)
    write_jsonl(out_dir / "violations.jsonl", violations)
    write_jsonl(out_dir / "qa_pairs.jsonl", qa_pairs)
    # Strip internal keys before writing report
    report = {k: v for k, v in validation_report.items() if not k.startswith("_")}
    write_json(out_dir / "validation_report.json", report)
    if dataset_manifest is not None:
        write_json(out_dir / "dataset_manifest.json", dataset_manifest)
