#!/usr/bin/env python3
"""
W3 ContractCard Verification Harness
=====================================
Takes each ContractCard, stands up a clean disposable sandbox (mktemp -d),
runs its `smoke` check, and assigns a TRUST RUNG with ZERO human per card.

Trust rungs (monotonic ladder, highest achieved wins):
  0 drafted        - card exists, never executed
  1 imports        - dependency installs + symbol imports/links (build-level)
  2 smoke-passes   - the card's own smoke check ran and printed OK / exited 0
  3 fixture-passes - smoke ran AND a behavioral assertion in it held (OK token)

smoke_tier (from WILD-semantic-contract insight):
  self   - runs fully offline, exercises real behavior      -> can reach rung 3
  import - external-service lib (DB/HTTP/API); offline we can
           only prove install+import/build, not live behavior -> caps at rung 1
  live   - needs a live external service to do ANYTHING       -> caps at rung 1 offline

The smoke string in the card IS the test. We execute it verbatim in a clean
sandbox. The installed library is the judge: a wrong card-derived guess gets
rejected by the toolchain, not waved through.

Provenance: every run writes raw stdout/stderr/exit to results/<card_id>.json
so a verdict is attributable, never asserted.
"""
import json, os, re, shutil, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path

DB = os.environ.get(
    "FOUNDRY_GITHUB_DB",
    str(Path.home() / ".local" / "share" / "siso-foundry" / "domains" / "github" / "identity" / "identity.sqlite"),
)
RESULTS = os.environ.get("FOUNDRY_VERIFICATION_RESULTS", str(Path(__file__).resolve().parent / "results"))

# Clean PATH so node/go/python/cc/cargo all resolve regardless of caller env.
ENV = dict(os.environ)
ENV["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.path.expanduser("~/.cargo/bin") + ":" + ENV.get("PATH", "")
ENV["GOFLAGS"] = "-mod=mod"
# Keep go/npm quiet-ish; no interactive prompts.
ENV["CI"] = "1"
ENV["npm_config_yes"] = "true"
ENV["npm_config_fund"] = "false"
ENV["npm_config_audit"] = "false"

# Per-tier timeout (seconds). Go/Rust first-build can be slow (compile + module fetch).
TIMEOUT = {"node": 180, "go": 300, "python": 240, "c": 90, "rust": 360}

# ---- smoke_tier classification (self / import / live) -----------------------
# An external-service lib can only be smoked at import/build level offline.
# We detect this from the card's `requires` + the smoke string's own honesty note.
EXTERNAL_SERVICE = re.compile(
    r"reachable (Postgres|Redis|MySQL)|live (Postgres|Redis|DB)|api\.openai\.com|"
    r"api\.github\.com|OPENAI_API_KEY|GitHub token|outbound HTTPS",
    re.I,
)
IMPORT_LEVEL_SMOKE = re.compile(r"import-level|needs a (live|token|Postgres|Redis|DB)|live (call|query|op)", re.I)


def classify_tier(card):
    """self = exercises real behavior offline; import/live = external-service, cap at rung 1."""
    blob = (card.get("requires") or "") + " || " + (card.get("smoke") or "")
    if EXTERNAL_SERVICE.search(blob) or IMPORT_LEVEL_SMOKE.search(card.get("smoke") or ""):
        return "import"  # offline we can only prove install+import/build
    return "self"


def lang_runner(card):
    lang = (card.get("language") or "").lower()
    if "javascript" in lang or "typescript" in lang:
        return "node"
    if "rust" in lang:
        return "rust"
    if lang == "c" or "c++" in lang:
        # hnswlib/annoy ship python bindings; their smoke is `python -c ...`
        if (card.get("smoke") or "").strip().startswith("python"):
            return "python"
        if "c++" in lang:
            return "python"  # bindings path
        return "c"
    if lang.startswith("go"):
        return "go"
    if lang.startswith("python"):
        return "python"
    # fall back: sniff the smoke command
    s = (card.get("smoke") or "").lstrip()
    for k in ("node", "go ", "python", "cargo", "cc "):
        if s.startswith(k.strip()):
            return {"go": "go", "cargo": "rust", "cc": "c"}.get(k.strip(), k.strip())
    return "node"


def node_packages(smoke):
    """
    JS/TS smoke strings exercise behavior but assume the npm package is already
    installed (the install is in the card's `recipe`, not the smoke). Derive the
    package name(s) from the smoke's own import/require so we install exactly what
    the card uses, then run the smoke against it.
    """
    pkgs = set()
    # import X from 'pkg'  /  import {..} from 'pkg'  /  import * as z from 'pkg'
    for m in re.finditer(r"""from\s+['"]([^'"]+)['"]""", smoke):
        pkgs.add(m.group(1))
    # require('pkg')
    for m in re.finditer(r"""require\(\s*['"]([^'"]+)['"]\s*\)""", smoke):
        pkgs.add(m.group(1))
    # normalize subpath imports (nanoid/non-secure -> nanoid) but keep @scope/name
    norm = set()
    for p in pkgs:
        if p.startswith("@"):
            norm.add("/".join(p.split("/")[:2]))
        else:
            norm.add(p.split("/")[0])
    return sorted(norm)


# card_id -> the pip distribution name(s) the smoke needs (import name != dist name).
PY_DIST = {
    "nmslib-hnswlib": ["numpy", "hnswlib"],
    "spotify-annoy": ["annoy"],
    "openai-openai-python": ["openai"],
    "redis-redis-py": ["redis"],
}


def unescape_heredoc_smoke(smoke):
    """
    Cards authored for Go/Rust/C embed literal `\n` between heredoc lines so the
    multi-line program survives as a single DB string. When we run via bash -c,
    those `\n` must become real newlines so the heredoc body is correct.
    Only the heredoc/source bodies need it; bash itself is newline-agnostic here.
    """
    # Turn the escaped-newline sequences into real newlines.
    return smoke.replace("\\n", "\n")


def run_smoke(card, runner):
    """Execute the card's smoke check in a fresh sandbox. Return raw evidence."""
    sandbox = tempfile.mkdtemp(prefix=f"verify_{card['card_id']}_")
    smoke = card["smoke"]
    t = TIMEOUT.get(runner, 180)
    started = time.time()
    try:
        if runner == "c":
            # cJSON: smoke needs cJSON.c + cJSON.h fetched (vendored, no package mgr).
            # Fetch the two source files from the pinned repo into the sandbox.
            for fn in ("cJSON.c", "cJSON.h"):
                url = f"https://raw.githubusercontent.com/DaveGamble/cJSON/master/{fn}"
                r = subprocess.run(["curl", "-fsSL", "-o", os.path.join(sandbox, fn), url],
                                   capture_output=True, text=True, timeout=30, env=ENV)
                if r.returncode != 0:
                    return dict(ok=False, exit=r.returncode, stdout="", stderr=f"fetch {fn} failed: {r.stderr}",
                               secs=round(time.time() - started, 1), sandbox=sandbox, fetched=True)
        import_ok = None  # None = phase not applicable (go/rust/c install inline in smoke)
        if runner == "node":
            # Phase 1 (rung 1 = imports): npm install the carded package(s) + prove import links.
            pkgs = node_packages(smoke)
            if not pkgs:
                return dict(ok=False, exit=-1, stdout="", stderr="could not derive npm package from smoke",
                           secs=round(time.time() - started, 1), sandbox=sandbox, import_ok=False)
            subprocess.run(["npm", "init", "-y"], cwd=sandbox, capture_output=True, text=True, timeout=30, env=ENV)
            inst = subprocess.run(["npm", "install", "--no-save", "--no-audit", "--no-fund", *pkgs],
                                  cwd=sandbox, capture_output=True, text=True, timeout=t, env=ENV)
            if inst.returncode != 0:
                return dict(ok=False, exit=inst.returncode, stdout=inst.stdout[-2000:],
                           stderr=("npm install failed:\n" + inst.stderr)[-4000:],
                           secs=round(time.time() - started, 1), sandbox=sandbox, import_ok=False)
            # Make the smoke's bare `import 'pkg'` resolve from the sandbox node_modules.
            # ESM eval needs NODE_PATH; bare specifiers resolve from cwd's node_modules already.
            import_ok = True

        py = "python3"  # smoke strings say bare `python`; this box only has python3
        if runner == "python":
            # Phase 1 (rung 1 = imports): pip-install the carded dist(s) into an isolated
            # venv, then prove import. Bindings (hnswlib/annoy) compile or pull a wheel.
            dists = PY_DIST.get(card["card_id"], [])
            venv = os.path.join(sandbox, ".venv")
            subprocess.run([py, "-m", "venv", venv], cwd=sandbox, capture_output=True, text=True, timeout=120, env=ENV)
            vpip = os.path.join(venv, "bin", "pip")
            vpy = os.path.join(venv, "bin", "python")
            if dists:
                inst = subprocess.run([vpip, "install", "-q", *dists], cwd=sandbox,
                                      capture_output=True, text=True, timeout=t, env=ENV)
                if inst.returncode != 0:
                    return dict(ok=False, exit=inst.returncode, stdout=inst.stdout[-2000:],
                               stderr=("pip install failed:\n" + inst.stderr)[-4000:],
                               secs=round(time.time() - started, 1), sandbox=sandbox, import_ok=False)
            import_ok = True
            py = vpy  # run the smoke with the venv's python so installed dists resolve

        cmd_smoke = smoke
        if runner in ("go", "rust", "c"):
            cmd_smoke = unescape_heredoc_smoke(smoke)
        if runner == "python":
            # rewrite the leading bare `python` invocation to the venv python
            cmd_smoke = re.sub(r"^\s*python\b", py, smoke)
        # Phase 2 (rung 2/3 = smoke/fixture): run the card's behavioral smoke verbatim.
        proc = subprocess.run(["bash", "-c", cmd_smoke], cwd=sandbox, capture_output=True,
                              text=True, timeout=t, env=ENV)
        return dict(ok=(proc.returncode == 0), exit=proc.returncode, stdout=proc.stdout[-4000:],
                   stderr=proc.stderr[-4000:], secs=round(time.time() - started, 1), sandbox=sandbox,
                   import_ok=import_ok)
    except subprocess.TimeoutExpired as e:
        return dict(ok=False, exit=124, stdout=(e.stdout or "")[-2000:] if isinstance(e.stdout, str) else "",
                   stderr=f"TIMEOUT after {t}s", secs=t, sandbox=sandbox)
    except Exception as e:
        return dict(ok=False, exit=-1, stdout="", stderr=f"harness error: {e}",
                   secs=round(time.time() - started, 1), sandbox=sandbox)
    finally:
        # Disposable: nuke the sandbox. Keep only the captured evidence.
        shutil.rmtree(sandbox, ignore_errors=True)


def assign_rung(tier, ev):
    """
    Map raw evidence -> trust rung.
      rung 0 drafted        : never reached here
      rung 1 imports        : exit 0 (install + import/build succeeded)
      rung 2 smoke-passes   : exit 0 AND tier==self (real behavior ran)
      rung 3 fixture-passes : smoke ran AND printed an explicit OK / true / behavioral token
    External-service ('import') tier is CAPPED at rung 1 offline even if exit 0,
    because all we proved is the symbol links, not that it does the thing.
    """
    if not ev["ok"]:
        # node: if install+import linked but the behavioral smoke failed, that's rung 1 not 0.
        if ev.get("import_ok") is True:
            return 1, "imports", "package installed + imported, but behavioral smoke failed"
        return 0, "drafted", "smoke did not pass (exit!=0)"
    out = (ev.get("stdout") or "")
    # GUARD: some cards print a fixed 'OK' token followed by the actual boolean assertion
    # (e.g. annoy `print('OK', len(n)==3)` -> 'OK False' when the assertion FAILED).
    # The literal 'OK' is not proof; a trailing False/false is a behavioral failure.
    assertion_false = bool(re.search(r"\b(OK|RESULT)\b[^\n]*\bFalse\b", out) or re.search(r"^\s*false\s*$", out, re.I | re.M))
    has_ok = bool(re.search(r"\bOK\b|^true\b|\btrue\s*$|import-ok|^8080|^ran\b", out, re.M | re.I))
    if tier == "import":
        # offline ceiling: install+import/build only
        return 1, "imports", "external-service lib: import/build proven, live behavior not testable offline"
    # tier == self
    if assertion_false:
        return 2, "smoke-passes", "smoke exited 0 but its own behavioral assertion was False (defective/forgiving smoke)"
    if has_ok:
        return 3, "fixture-passes", "smoke ran and behavioral assertion (OK/true token) held"
    return 2, "smoke-passes", "smoke exited 0 but no explicit OK token observed"


def main():
    os.makedirs(RESULTS, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cards = [dict(r) for r in con.execute(
        "SELECT card_id, full_name, language, band, requires, smoke FROM bank_contractcard ORDER BY language, card_id")]

    only = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    summary = []
    for card in cards:
        if only and card["card_id"] not in only:
            continue
        tier = classify_tier(card)
        runner = lang_runner(card)
        if runner == "rust" and not os.path.exists(os.path.expanduser("~/.cargo/bin/cargo")):
            ev = dict(ok=False, exit=-1, stdout="", stderr="cargo not installed", secs=0, sandbox="")
        else:
            print(f"[run] {card['card_id']:<28} tier={tier:<6} runner={runner}", flush=True)
            ev = run_smoke(card, runner)
        rung, rung_name, reason = assign_rung(tier, ev)
        rec = dict(card_id=card["card_id"], full_name=card["full_name"], language=card["language"],
                   band=card["band"], smoke_tier=tier, runner=runner, trust_rung=rung,
                   rung_name=rung_name, reason=reason, exit=ev["exit"], secs=ev["secs"],
                   stdout_tail=(ev.get("stdout") or "")[-500:], stderr_tail=(ev.get("stderr") or "")[-800:])
        json.dump(rec, open(os.path.join(RESULTS, f"{card['card_id']}.json"), "w"), indent=2)
        summary.append(rec)
        print(f"      -> rung {rung} ({rung_name})  exit={ev['exit']} {ev['secs']}s", flush=True)

    json.dump(summary, open(os.path.join(RESULTS, "_summary.json"), "w"), indent=2)
    # breakdown
    from collections import Counter
    by_rung = Counter(r["rung_name"] for r in summary)
    by_tier = Counter(r["smoke_tier"] for r in summary)
    print("\n=== BREAKDOWN ===")
    print("tier :", dict(by_tier))
    print("rung :", dict(by_rung))
    print(f"total: {len(summary)} cards")
    con.close()


if __name__ == "__main__":
    main()
