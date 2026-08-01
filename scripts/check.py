#!/usr/bin/env python3
"""Repository-level source, fixture, and publication-safety checks."""

import json
import os
from pathlib import Path
import py_compile
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", "node_modules", "__pycache__", "run", "results"}


def source_files(suffix):
    return [path for path in ROOT.rglob(f"*{suffix}") if not IGNORED_PARTS.intersection(path.parts)]


def run(command, **kwargs):
    subprocess.run(command, cwd=ROOT, check=True, **kwargs)


for path in source_files(".py"):
    py_compile.compile(str(path), doraise=True)

for path in source_files(".mjs"):
    run(["node", "--check", str(path)])

for path in source_files(".sh"):
    run(["bash", "-n", str(path)])

run([sys.executable, "-m", "unittest", "discover", "-s", "pipelines/github", "-p", "test_*.py"], stdout=subprocess.DEVNULL)
run([
    sys.executable, "pipelines/github/run_campaign.py", "--dry-run",
    "--campaign", "pipelines/github/campaigns/agent-systems-v1.json",
], stdout=subprocess.DEVNULL)

with tempfile.TemporaryDirectory(prefix="siso-foundry-check-") as directory:
    env = dict(os.environ)
    env["FOUNDRY_TOPICS_DB"] = str(Path(directory) / "topics.sqlite")
    topics = ROOT / "packages" / "research-topics" / "topics.py"
    run([sys.executable, str(topics), "init"], env=env, stdout=subprocess.DEVNULL)
    run([sys.executable, str(topics), "list"], env=env, stdout=subprocess.DEVNULL)

manifest = json.loads((ROOT / "datasets" / "manifest.json").read_text())
assert manifest["work_id"].startswith("gls:work:")
assert manifest["assets"]
for asset in manifest["assets"]:
    assert asset["observed_bytes"] >= 0
    assert asset["publication_state"]
    assert asset["required_release_receipts"]

publication_patterns = [
    re.compile("/" + "Users" + "/"),
    re.compile("SISO_" + "Workspace"),
    re.compile("BEGIN (?:RSA |OPENSSH |EC |DSA )?" + "PRIVATE KEY"),
    re.compile("(?:ghp|github_pat|sk)" + "-[A-Za-z0-9_-]{16,}"),
]
for path in ROOT.rglob("*"):
    if IGNORED_PARTS.intersection(path.parts):
        continue
    if path.is_symlink():
        text = os.readlink(path)
    elif path.is_file():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
    else:
        continue
    for pattern in publication_patterns:
        if pattern.search(text):
            raise SystemExit(f"publication safety match {pattern.pattern!r} in {path.relative_to(ROOT)}")

print(f"FOUNDRY_CHECK_OK ({len(source_files('.py'))} Python files)")
