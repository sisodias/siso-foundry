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
    defaults = {
        "github": "identity.sqlite",
        "youtube": "queue.db",
        "books": "books.sqlite",
    }
    fname = name or defaults.get(domain, f"{domain}.sqlite")

    root = data_root()
    if domain == "github":
        # The github domain is multi-DB: identity is the people/repo spine,
        # awesome is the curated-list catalog. They live in sibling dirs.
        # Explicit map, not a filename prefix test -- the prefix version broke
        # silently when awesome_catalog.sqlite was renamed to
        # catalog_full.sqlite and started resolving into identity/.
        GITHUB_SUBDIR = {
            "identity.sqlite": "identity",
            "awesome_catalog.sqlite": "awesome",
            "catalog_full.sqlite": "awesome",
        }
        sub = GITHUB_SUBDIR.get(fname, "identity")
        return root / "domains" / "github" / sub / fname
    return root / "domains" / domain / fname


def github_awesome_db() -> Path:
    """The awesome-list catalog (curated-list membership + inherited sections).

    catalog_full.sqlite, not awesome_catalog.sqlite: the latter was built by
    crawling outward from one seed repo, and measured, that reached only ~27%
    of the ecosystem (73% of repos carrying topic:awesome are unreachable from
    sindresorhus/awesome). The full catalog ingests every cached README
    regardless of how it was discovered -- see pipelines/github/awesome/.
    """
    return domain_db("github", "catalog_full.sqlite")


# Convenience: the GitHub identity DB (the one ~all current scripts use).
def github_identity_db() -> Path:
    return domain_db("github", "identity.sqlite")


if __name__ == "__main__":
    print("FOUNDRY_DATA =", os.environ.get("FOUNDRY_DATA", "(unset)"))
    print("data_root()  =", data_root())
    print("github identity DB ->", github_identity_db())
    print("exists:", github_identity_db().exists())
