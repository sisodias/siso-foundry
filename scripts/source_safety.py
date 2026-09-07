#!/usr/bin/env python3
"""Scan publishable source, never ignored datasets; report rule IDs, not secrets.

This is a heuristic guard, not a proof of zero secrets or a rights/privacy review.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from typing import Iterable

RULES = {
    "personal_absolute_path": re.compile("/" + "Users" + "/"),
    "private_workspace_marker": re.compile("SISO_" + "Workspace"),
    "private_key": re.compile("BEGIN (?:RSA |OPENSSH |EC |DSA )?" + "PRIVATE KEY"),
    "github_token": re.compile(r"(?<![A-Za-z0-9])gh[pousr]" + r"_[A-Za-z0-9]{20,}"),
    "github_fine_grained_token": re.compile(r"(?<![A-Za-z0-9])github_pat" + r"_[A-Za-z0-9_]{20,}"),
    "api_key": re.compile(r"(?<![A-Za-z0-9])sk" + r"-[A-Za-z0-9_-]{16,}"),
    # Retain the previous conservative hyphen-prefix check as well.
    "legacy_token_candidate": re.compile(r"(?<![A-Za-z0-9])(?:ghp|github_pat)" + r"-[A-Za-z0-9_-]{16,}"),
}


def matching_rules(text: str) -> list[str]:
    return [name for name, pattern in RULES.items() if pattern.search(text)]


def repository_files(root: Path) -> list[Path]:
    """Tracked plus nonignored candidates; no recursive private-data crawl."""
    root = root.resolve()
    top = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=root, stderr=subprocess.PIPE
    ).decode().strip()
    if Path(top).resolve() != root:
        raise ValueError("Expected the repository root")
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, stderr=subprocess.PIPE,
    )
    paths = []
    for item in sorted(set(raw.split(b"\0")) - {b""}):
        relative = Path(os.fsdecode(item))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe source path returned by Git")
        path = root / relative
        # Do not traverse a symlinked parent into external evidence.
        parent = path.parent
        while parent != root:
            if parent.is_symlink():
                raise ValueError("Source path traverses a symlinked directory")
            parent = parent.parent
        if path.is_symlink() or path.is_file():
            paths.append(path)
    return paths


def scan(root: Path, paths: Iterable[Path] | None = None) -> list[dict]:
    root = root.resolve()
    findings = []
    for path in repository_files(root) if paths is None else paths:
        # Read the link text, never its target. Decode ASCII patterns in binary
        # files too; a non-UTF-8 byte must not bypass credential detection.
        text = os.readlink(path) if path.is_symlink() else path.read_bytes().decode("utf-8", errors="ignore")
        rules = matching_rules(text)
        if rules:
            findings.append({"path": path.relative_to(root).as_posix(), "rules": rules})
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        findings = scan(root)
    except (OSError, ValueError, subprocess.CalledProcessError):
        print(json.dumps({"check": "publication_safety", "status": "error", "reason": "source_scan_unavailable"}))
        return 2
    print(json.dumps({"check": "publication_safety", "status": "fail" if findings else "pass", "findings": findings}))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
