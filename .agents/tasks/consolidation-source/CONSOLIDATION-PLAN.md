# Great Library estate consolidation plan
Derived 2026-08-07 by reading branch contents directly (not filenames).

## Verified facts

- 11 repos with pushes since 2026-08-01; 109 branches total.
- Library estate = 4 repos, **37 branches carrying commits**, **0 PRs ever merged**.
- Great Library: 20 branches ahead of main, **16,552 unique lines / 109 files**.
  Split by area: research/ 10,964 (66%) | docs/ 3,291 | registry/ 1,978 | site/ 213 | schemas 28.
- Two designed lanes NEVER shipped: Lane 5 (reproducible builds), Lane 6 (query/API/MCP).
  These own the fixers for PGRT-001 (clean build) and PGRT-004/PG-AUDIT-002 (ask.py ignores
  accepted claims). So 2 of 8 P0s have no shipped fix.
- `Lordsisodia` is 404 as user AND org. Commit authorship on siso-librarian + siso-foundry
  is unattributable on GitHub's side. Program docs already flag this: "historical references
  under a different GitHub owner remain a verification and migration question, not an assumed alias."
- Real commit counts (paginated): oracle 594, siso-librarian 286 since Aug 1.

## Consolidation map (20 GL branches -> 8 bodies of work)

### Maths: 12 branches -> 1. SELF-CONSOLIDATING.
`agent/erdos-09-23` CONTAINS all 11 others (verified via merge-base --is-ancestor), including
`agent/unsolveable-mathematics-program` and `agent/erdos-10-campaign-2026-08-07`.
=> New repo cut from erdos-09-23. Delete other 11, zero loss.
Content: UNSOLVEABLE constitution (359 lines), Erdos master prompt (348), Erdos-41 flagship
dossier (156), source synthesis (108), agent-09 Erdos-23 workspace (13 files).
Agent 09 produced a real conditional partial result: closes 147 orders through 200, every
order <= 42, first unclosed = 43. Labeled NEW CANDIDATE PARTIAL RESULT, not solved.

### Research departments: 3 branches -> 1 or 2.
`agent/remote-viewing-research-module` (25 commits) and `agent/psychoenergetics-terrain-scan`
forked at c9e4876; share 18 commits + 17 files. Neither contains the other. Trivial reunion.
`agent/declassified-government-records-department` standalone (1 commit, 2067 lines).
Contains real code: target_manager.py (463) + tests (183), verify_module.py (334).
=> Own repo(s). Code+tests do not belong in a metadata catalog.

### People Graph program: 4 branches -> merge to GL main.
No containment between them - by design, "intentionally non-overlapping". One investigation
split by artifact type:
- `gls/people-graph-parallel-spine-20260806` (26 commits) - ADR-0005, Works, Releases, V37,
  GQ-010, pg-observation-0.1, schema+site changes. THE CONTROL PLANE.
- `agent/people-graph-audit-record-20260806` (15) - findings.json PG-AUDIT-001..013, each
  pinning exact blob revisions. complete-decision-record.md (509 lines).
- `gls/people-graph-source-research-20260806` (8) - 39-source matrix, rights/deletion matrix,
  10 value theses, 30/90/180-day pilot portfolio (101-163 eng-days, $4,750-$24,000).
- `agent/first-principles-people-graph-program-2026-08-06` (4) - R1-R10, value function.

### Local unpushed: `register-graph-and-book-library` (6163146). NOT on GitHub. Push first.

## Merge order (GL)

0. Push `register-graph-and-book-library` - only copy is this laptop.
1. `gls/people-graph-parallel-spine-20260806` - control plane, additive schema only,
   modifies no immutable record. Verify: `npm ci && npm run check:immutable && npm run verify`.
2. Docs-only lanes (no conflict risk): source-research, first-principles, audit-record.
3. Successor Event recording 11-of-13 truth (NEVER edit the immutable launch Event).
4. Cut maths repo from erdos-09-23; delete 11 erdos branches.
5. Cut research-department repo(s); delete those branches.
6. Register new repos as Works in GL with source_repository locators (same pattern as
   People Graph / Book Library).

## Blocking gate (from the program's own handoff-registry.md)

Merge consideration #3: "Require all thirteen draft handoffs before selecting a production
schema or database migration." Two handoffs don't exist => CANNOT select production schema.
Does NOT block: merging the spine, docs lanes, or PR#3 as an *additive parallel* schema.

## Data-integrity item

`registry/works/siso-people-graph.json` cites person=339,217 / person_person=1,272,495 /
org=1,131 as `integration_check` evidence with verified:true. Red-team PGRT-002/003/009/016
show these are not defensible as *distinct-human* counts (name fusion, 0.98 attribute
auto-accept, CJK collapse to ","). Amend the evidence summary BEFORE merging - cheap now on
an unmerged branch, an immutable-record correction later.

## What the 20 grand actually bought (read in full, not summarised)

The scarce resource is NOT data. Ledger §10: "Public data is abundant. The scarce resources
are trustworthy canonical identity, source-grounded attribution, exact evidence
addressability, temporal and rights context, reversible correction, release reproducibility,
and disciplined question demand. The first 100x improvement is a trust improvement before it
is a scale improvement."

### The unifying diagnosis (reasoning-ledger Step 12) - ELEVEN CATEGORY COLLAPSES
source actor -> canonical person | account -> actor | owner -> creator |
work subject -> person topic -> possible belief | lifespan overlap -> contemporaneity ->
actual conversation | shared attribute -> shared identity | heuristic score -> probability |
popularity metric -> universal value | source item -> abstract Work | reference -> evidence |
indexed result -> complete output
Every P0 is an instance of one. => "the architecture needed a source/decision/projection
separation rather than isolated bug fixes." Fixing thresholds individually leaves the class intact.

### Quantified blast radius (Step 5)
Matcher pairs every record in a repeated (platform,value) group: n(n-1)/2.
100 people at one company = 4,950 false pairs AT 0.98 CONFIDENCE. Not a weak queue - it
floods the highest-trust path.

### Silent-failure bugs found by reproduction (Steps 6-7)
- `who()` uses `people.person_search MATCH ?` -> "no such column" -> app catches ANY SQLite
  error -> silently falls back to LIKE scan. Query LOOKS like it works.
- `works()` caps at 200 rows, reports count=len(rows), no truncation flag. Caller cannot
  distinguish 5 results from 200-of-40,000.
Lesson: "query tests must prove which execution path ran, not merely that a result was
eventually returned."

### Rejected alternatives (Step 14) - preserved reasoning
better name normalisation ("cannot make names unique"); account IDs as canonical
("breaks on handle changes"); replace SQLite ("engine choice does not repair semantic
corruption"); extract claims from everything (fails token economics); build viewer first
("presentation can amplify false certainty"); one global importance score.

### The programme reversed its own earlier advice (§5)
First answer = expand sources. Re-derivation moved identity safety from a research track to
the FIRST engineering priority; "belief graph" -> source-grounded public STATEMENT model;
Book Library -> export producer, not direct graph writer; viewer moved LAST.

### EXECUTABLE VERIFIERS EXIST
`tools/verify_audit_findings.py` on branch `agent/first-principles-audit-2026-08-06` in BOTH
siso-people-graph and siso-book-library. Re-checks every finding. This is the mechanism to
confirm which defects still reproduce after any fix. RUN THESE FIRST.

### The two unshipped lanes are RECOVERABLE - full work orders survive
parallel-slam.md Prompt 5 (reproducible builds) and Prompt 6 (query surface) are COMPLETE
specs, 11 and 10 numbered items with acceptance criteria - they just never ran.
Prompt 5: "Fix clean-checkout schema/path resolution and test it from a temporary directory"
+ two clean builds with equal logical digests. => fixes PG-AUDIT-004/PGRT-001.
Prompt 6: owns `loaders/ask.py`, resolver must "expose accepted/proposed claim state and
ambiguity honestly" + "Missing capabilities must be explicit in output". => fixes
PG-AUDIT-002/PGRT-004 and PGRT-015.
You are not re-deriving the design, only executing it. Cheapest high-value work available.

### The 20 drafts are the SPECIFIED output, not a failure
parallel-slam.md closing: "Some will be merge-ready; some will reveal incompatible
assumptions or produce pilots that should be killed. That is expected." Design intended 13
independently-EVALUABLE proposals + a harness (Prompt 13) to assess any subset.
Prompt 13 even pre-authorised the empty-PR case: "If no PR exists yet, write the review
template and current-main baseline" - which is exactly what it did.

### Book Library triplicate EXPLAINED
Prompt 7 acceptance demands TWO clean fixture builds with EQUAL LOGICAL DIGESTS plus
stale-edge, queue-dedup, locator-checksum, role-preservation, envelope-export tests.
-1/-2/-3 are three attempts at a hard bar. Persistence, not mess. Merge -3, close -2.

### They already found the empty-branch problem
prompt-evolution.md: "A later GitHub audit showed that several branch names existed but were
identical to main. This record explicitly distinguishes branch reservation from durable
pushed work." Correct finding, written down, on an unmerged branch nobody can see.
THAT IS THE WHOLE PROBLEM IN ONE SENTENCE: the work isn't lost, it's unreachable.

### Why 20 branches existed (prompt-evolution.md)
Execution surface was ChatGPT/Codex web UI: one chat cannot launch child agents, wait on
branch completion, or hand results to the next lane. Dependency graph would have created
idle agents + made Shaan the human scheduler. So dependencies were replaced by: current-main
starts, exclusive path ownership, additive compatibility shims, draft-PR handoff.
THE BRANCHES WERE THE ORCHESTRATOR. That constraint is gone now => collapse them.

## Research departments - READ IN FULL, verdict: these are GOOD and belong in own repos

### Remote viewing (~3,500 lines, 25 commits) - the strongest non-PeopleGraph work
THREE-TRACK TRUTH BOUNDARY: practice track "assume enough to execute"; evidence track
"assume nothing in the analysis"; theory track "force hypotheses to compete". This is what
lets a practitioner work from a possibility premise while the Library stays honest.

Core rule 6: above-chance scoring / paranormal cause / specific mechanism / trainability /
operational usefulness are FIVE DIFFERENT CLAIMS. Most writing collapses them.

claims.json = 33 claims. Distribution: 14 not_established, 11 documented_record,
2 reported_positive, 2 reported_negative, 3 methodological_rule, 1 unknown. Every claim has
an `update_gate` = the exact evidence that would change its status.
- RV-C016 (US spent billions + classified successor exists) = **unknown**: "Wider
  intelligence infrastructure costs are not evidence of a remote-viewing budget, and absence
  of public evidence is not proof."
- RV-C017 (renaming proves it worked) = **not_established**.
- RV-C003 (AIR found above-chance lab results) = documented_record, AND
  RV-C004 (AIR established operational value) = reported_negative. Same source, honest split.

experimental-method.md: 7 distinct claim types each needing a different design; 15-item
preregistration contract frozen before first cue; "timestamp the registration in a system not
controlled by the analyst... a Git commit should not replace an external preregistration".
Best line: "Do not place one waterfall among three office interiors and celebrate 'water'."
And: "The cue is an arbitrary task handle, not evidence that geographic coordinates carry
information" - refuses the coordinate-RV mythology while keeping the practice usable.

tools/target_manager.py (463 lines + 183 test): SHA-256 commitment = SHA256(nonce||target),
transcript lock before feedback, tamper detection. HANDOFF lists what it does NOT do:
doesn't encrypt, doesn't make self-run double-blind, doesn't build balanced decoys, doesn't
score, "does not establish target correspondence or paranormal ability."

**IT ALREADY KNOWS IT DOESN'T BELONG IN THE CATALOG.** HANDOFF says the isolated path was
chosen because active lanes owned Snapshot/CURRENT_STATE/site/root-indexes. It specifies a
NINE-STEP promotion sequence ending in an independently addressable Work + immutable Release.
=> Move to own repo, register as Work w/ source_repository locator. Gate: 10 clean pilot
sessions + independent review by one sympathetic AND one critical reader.

### Declassified Government Records (~1,900 lines, 1 commit)
FOUR-TRUTH MODEL: record truth (what the document literally contains) | custody+release truth
(how it reached the public) | source-asserted truth (what the record's author claims) |
research conclusion. Rule: "The system must never silently move from source-asserted truth to
research conclusion." That is the distinction conspiracy-adjacent research always collapses.

Correct legal precision: "FOIA release and declassification are not synonyms." Taxonomy
separates formal declassification / FOIA / MDR / systematic review / statutory special
collections / archival-open (never classified).

rights-safety-and-ethics.md: 4 safety tiers (standard, enhanced_privacy, hazardous_technical,
restricted_metadata_only). Key principles:
- "Do not assemble a capability manual from individually public records" (aggregation risk)
- "Official release does not eliminate risk"
- "A name in an intelligence or law-enforcement file is not proof of guilt, affiliation,
  reliability, or agency employment" -> directly constrains future People Graph links
- "must not become a sensational highlight reel" - preserve mundane provenance, null
  findings, documents showing institutional error
Explicitly does NOT own: leaked/unlawfully obtained material, current intelligence
collection or operational targeting, the RV module, UNSOLVEABLE.

### Topology verdict
research/ = 10,964 of 16,552 lines (66%) of GL branch content. The GL's own README says
"a catalog, not a giant monorepo"; ADR-0005 rejected storing the PG database for the same
reason. target_manager.py + tests + verify_module.py are working code with tests inside a
metadata registry - same category error, different content.
=> 3 new repos: maths (from erdos-09-23), remote-viewing(+psychoenergetics), DGR.
Each registered as a GL Work with a source_repository locator. GL keeps ~2,300 lines of
genuine control-plane records on one main.

## MULTI-REPO REALITY (measured 2026-08-07) - GL is only 1/5 of the corpus

| repo | unique lines | files | note |
|---|---:|---:|---|
| siso-people-graph | 37,242 | 248 | THE BULK. 9 live branches. |
| siso-foundry | 15,384 | 31 | 2 branches, no PRs ever opened |
| great-library-of-siso | 16,552 | 109 | READ IN FULL this session |
| siso-book-library | 9,493 | 89 | 3 successive refinements + audit |
| **TOTAL** | **78,671** | **477** | |

PRESERVATION NOW CLOSED: all three repos cloned to scratchpad (first local copies
ever). Previously ~62k lines existed ONLY on GitHub.

### People Graph branch sizes
6687 pg/v3-ontology-schema | 5876 pg/living-creators-media-pilot |
4804 pg/red-team-fixtures | 4712 pg/parallel-integration-contract |
4655 pg/software-ai-pilot | 3900 agent/people-graph-100x-research-dossier |
3505 pg/identity-resolution-parallel | 2938 agent/first-principles-audit |
165 pg/claims-temporal-relations (UNDER-DELIVERED: declared claims/**, projections/**,
tests/claims/**, docs/reasoning/** - shipped only 2 GitHub Actions files) |
0 pg/scholarly-authority-pilot (EMPTY - branch reserved, never pushed) |
0 agent/people-graph-source-expansion-dossier (EMPTY)

=> **THREE lanes effectively did not deliver**, not two: Lane 5 (reproducible builds,
no branch), Lane 6 (query surface, no branch), Lane 9 (scholarly pilot, branch exists
at 0 lines). Plus Lane 12 (claims) at 165 lines of the wrong thing.
Delivered properly: 8 of 13.

### Biggest unread artifacts (siso-people-graph)
docs/first-principles/README.md (1131) | docs/first-principles/agent-program.md (908) |
schema/v3/design_provenance.json (718) | docs/research/people-graph-100x/
architecture-and-100-tracks.md (603) | docs/audits/receipts/*run*.json (572) |
decision-log.md (529) | evidence-ledger.json (473) | forensic-worklog (448) |
agent-missions.md (445) | sources/creators/envelope.py (439) | tools/
verify_audit_findings.py (410) | identity_v3/adapters.py (398) | integration/
contract_validation.py (390) | integration/merge_risk.py (312)

## v0 SUPERSEDED PACK - what the parallel redesign LOST

dependency-ordered-superseded.md (684 lines) had Prompt 0 = a COORDINATOR whose PR
merged BEFORE parallel work, so "conflicts are visible on canonical main before
parallel work begins". Real dependency chain: red-team -> schema -> identity/build
-> pilots -> integration last.

**Prompt 12 was dropped entirely by the parallel redesign.** It was a cross-repo
adversarial RELEASE GATE with 8 named gates including "Regression: run Prompt 1's
original failure fixtures and prove the selected P0s are resolved" and the rule
"do not paper over a red gate". It also owned: registering Works, immutable Release
manifests "for the code/data-contract versions actually proven - not for unbuilt
production data", snapshot, and the closing Event.

Parallel Prompt 13 replaced it with a compatibility HARNESS that could run at launch.
Correct for the tool constraint, BUT: nobody owns the final release gate. 13 evaluates
compatibility; 12 would have PROVEN the P0s fixed and published the closing Event.
=> Recoverable: the spec survives. This is the missing convergence step.

Both unshipped lanes have specs in TWO independent versions (v0 Prompts 4+5, parallel
Prompts 5+6). Maximally recoverable.

## FOUNDRY `crates-and-relational-layer` = THE MOST VALUABLE UNMERGED BRANCH
1 commit, no PR ever opened. docs/PEOPLE-GRAPH-ENRICHMENT-LOG.md (647 lines) is the
empirical origin of the whole 100x thesis. 6 rounds, every number re-derived
independently with json_extract rather than trusting the loader's own counters.

### THE core measurement everything downstream cites
Of 280,708 people, exactly THREE span >1 domain: Karpathy, Jensen Huang, Simon
Willison. That is the "structural overlap gap", measured at source.

### NEGATIVE RESULT #8 - github<->book identity stitch is STRUCTURALLY DEAD
Join resolved GitHub real_name against book author names => 2 matches, BOTH false
positives (gh:gildas-lormeau -> bk:gildas|516-570, a 6th-century monk;
gh:parallax -> bk:parallax|1816-1884). Restrict to plausible human names => ZERO.
Two measured causes: (a) Gutenberg is public-domain, populations don't overlap in
time - only 419 book people could plausibly be alive in the GitHub era, that is
the THEORETICAL CEILING; (b) GitHub real_name is free text - orgs fill it with
".NET Core Community", "/r/freemediaheckyeah".
=> "must not be sold as the stitch fix. Cross-domain reach needs a contemporary
corpus. That, not name resolution, is the real blocker." THIS IS WHY the People
Graph program pivoted to living technical creators.

### NEGATIVE RESULT #5 - person<->person co-membership REJECTED
720,107,620 naive pairs. "both wrote a CLI utility" is not a relationship.
"Recorded here so it is not re-attempted naively."

### NEGATIVE RESULT #14 - source diversity is a restatement of stars
Looked compelling (avg_value 48.7->69.5). But "sources" are our own crawl batches,
STAR-BANDED BY CONSTRUCTION (urls_ge5k, urls_10k_50k). Control for stars within
one band => collapses.

### NEGATIVE RESULT #12b - do not parse the rich prose column
bank_gold.why (29,937 human rationales) contains license lanes but the same
license appears >=4 ways. Used repo_category.legal_lane instead - "the same
judgement in a proper column". Lesson: "'there is 29,937 rows of rich text' is
exactly the kind of seam that looks more valuable than the boring structured
column next to it."

### PREMISE CORRECTION that saved a build
Brief said "a whole YouTube domain DB barely represented". `ls domains/` = github,
people only. Entire YouTube corpus = 97 rows; graph already has 97 YouTube edges.
"YouTube is not under-loaded; it is fully loaded... Chasing a YouTube loader would
have been wasted work."

### WHAT WAS BUILT (idempotency verified on every loader by re-running --apply)
- #1/#2 rated value + 264 curated categories: 303,114/303,116 owners matched
  (99.9993%). dtolnay (10 repos >=90, 30,910 stars) ranks ABOVE facebook (801,473
  stars). "That inversion is the entire point: invisible to a star-ranked graph."
- #3 awesome editorial signal: 53,072 of 85,608 cited owners matched. Weight =
  log1p(distinct lists) because "one list citing an owner forty times is one
  editor's opinion, not forty". Caveat recorded not hidden: top is microsoft/
  google/apache, so stored as cited-ness NEVER as a "great engineer" score.
- #9/#10 recency/lifecycle: 463,221 edges gain pushed_at. FIXED observed_at
  semantics - column meant "when it was true" but held the load timestamp.
- #6 adoption: yargs-parser = 517 stars but 4,384,968 dependent repos.
  emoji-regex = 1,909 stars, 4.19M dependents. Finds the UNDERRATED.
- #4 TOPIC BRIDGE - the real fix for cross-domain. 819 topic strings appear
  verbatim in BOTH lcsh and github_topic => 22,466 people reachable from one
  predicate. Parker Hitt (1916 military ciphers) returns alongside Filippo
  Valsorda (Go crypto). EXACT MATCH ONLY, no stemming/embeddings, because "fuzzy
  matching generates plausible-looking garbage - precisely the failure mode the
  name-stitch already demonstrated". 57-term stopword gate.
- #11 momentum: 56,933 edges. HONEST SCOPE stated - 3 consecutive days in July
  2026, "a momentary reading, not a trend", deliberately NOT folded into rank_score.
- #15 passages: 606 book edges gain readable-text flag. "A flag, not the text."
- #12 legal lane: 9,605 edges; 5,801 shippable, 1,006 blocked. `unknown` loaded
  DELIBERATELY - "we looked and could not tell" != "we never looked".

### COMPOUNDING RESULT
313,845 edges now carry >=2 independent quality signals, up from ZERO.
person_topic 1,661,361 -> 2,050,629. NO people created, NO rows added - enriched
in place. This is "trust density over row density" actually executed.

### TWO REUSABLE ENGINEERING LESSONS
1. An index on `col` does NOT serve `lower(col)`. 1,638 full scans of 2M rows,
   still running after 15 min; rewritten as one set-based sweep = 1.33s, >600x.
2. `meta_json LIKE '%key%'` matches VALUES as well as keys. Reported baseline 35
   instead of 0 because 3 repos were literally named "velocity". All headline
   numbers re-derived with json_extract.

## THREE COMPETING LANE SCHEMES - a real consolidation hazard
1. v0 dependency-ordered: Prompts 0-12 (superseded, never launched)
2. parallel-slam: Prompts 1-13 (THE ONE ACTUALLY LAUNCHED)
3. PG first-principles agent-program.md: Lanes 00-12 (different tree again)
"Lane 5" means three different things depending on the document. Pick ONE
canonical numbering during consolidation or this will cause a mis-merge.

## Preservation (decouple from integration)

No local clone of siso-people-graph or siso-book-library exists anywhere on this machine.
~37,000 lines exist ONLY on GitHub. An account in this estate has already vanished
(Lordsisodia). Mirror-clone all 4 repos + bundle, store off-machine. Zero judgment required;
do not couple this to the merge decisions.
