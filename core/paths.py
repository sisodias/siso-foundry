"""Foundry — single source of truth for WHERE the data lives.

The ONE indirection (FOUNDRY-PLAN.html law #3): every Foundry script resolves its
domain DB through this module, so identical code finds the right file on either
machine:
  - Mac mini (engine):  FOUNDRY_DATA -> the 5TB vault Foundry dir (canonical, writable)
  - laptop (cockpit):   FOUNDRY_DATA -> a local non-canonical read-only snapshot

Resolution order for the data root:
  1. $FOUNDRY_DATA                      (explicit override; what launchd sets on the mini)
  2. ~/.local/share/siso-foundry        (portable user-local default)
"""
import os
from pathlib import Path

def data_root() -> Path:
    """The configured Foundry data root."""
    env = os.environ.get("FOUNDRY_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".local" / "share" / "siso-foundry"


def domain_db(domain: str, name: str = None) -> Path:
    """Resolve a domain's primary DB path.

    domain: 'github' | 'youtube' | ...
    name:   db filename; defaults per domain.
    """
    defaults = {"github": "identity.sqlite", "youtube": "queue.db"}
    fname = name or defaults.get(domain, f"{domain}.sqlite")

    root = data_root()
    if domain == "github":
        return root / "domains" / "github" / "identity" / fname
    return root / "domains" / domain / fname


# Convenience: the GitHub identity DB (the one ~all current scripts use).
def github_identity_db() -> Path:
    return domain_db("github", "identity.sqlite")


if __name__ == "__main__":
    print("FOUNDRY_DATA =", os.environ.get("FOUNDRY_DATA", "(unset)"))
    print("data_root()  =", data_root())
    print("github identity DB ->", github_identity_db())
    print("exists:", github_identity_db().exists())
