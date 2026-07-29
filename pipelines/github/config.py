"""Portable paths shared by the GitHub Foundry pipeline."""

import os
from pathlib import Path


def data_root() -> Path:
    return Path(os.environ.get("FOUNDRY_DATA", Path.home() / ".local" / "share" / "siso-foundry")).expanduser()


def github_db() -> Path:
    override = os.environ.get("FOUNDRY_GITHUB_DB")
    return Path(override).expanduser() if override else data_root() / "domains" / "github" / "identity" / "identity.sqlite"


def github_domain_dir() -> Path:
    return github_db().parent.parent


def raw_dir() -> Path:
    return github_domain_dir() / "raw"


def staging_dir() -> Path:
    return github_domain_dir() / "staging"


def curated_dir() -> Path:
    return github_domain_dir() / "curated"


def shard_dir() -> Path:
    override = os.environ.get("FOUNDRY_GITHUB_SHARDS")
    return Path(override).expanduser() if override else data_root() / "incoming" / "github"


def artifact_dir() -> Path:
    override = os.environ.get("FOUNDRY_ARTIFACTS")
    return Path(override).expanduser() if override else data_root() / "artifacts"
