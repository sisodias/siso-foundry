# SISO Agency OS value matrix

The missing decision system is now explicit: Foundry does not ask whether a repository is “good.” It asks whether a particular repository can create value for a particular SISO use case through a particular adoption route.

```text
repository × SISO use case × adoption route
  -> gross Agency value
  -> feasibility and evidence
  -> priority lane and proof gate
  -> owner, release and outcome evidence
```

That distinction matters. A repository can be a God Source for one capability, a reference for another, and the wrong application shell overall.

## What “God Source” means

A **God Source** is a coherent source product or primitive that can remove a large block of product and delivery work across SISO itself, the reusable Agency Edition, and multiple client deployments. It must expose meaningful data or actions to agents, have a viable ownership route, and have source-read-or-better evidence.

It does **not** mean “copy the whole repository.” The correct route may be a source-owned fork, an intact managed service, a bounded library dependency, an infrastructure primitive, a clean-room pattern, or rejection.

The machine-readable matrix is [`value-matrix.json`](value-matrix.json). It contains the scoring contract, exact evidence states, proof gates and the first twenty cross-agency application entries.

## First cross-agency decision tranche

| Priority | Source × application | Value | Feasibility | Class | Current route |
|---:|---|---:|---:|---|---|
| 87 | Activepieces × governed automation runtime | 100 | 87 | God Source | Integrate next |
| 86 | SurveyJS × owned intake/forms primitive | 90 | 95 | God Source | Integrate next |
| 86 | Meilisearch × permissioned lexical search | 94 | 91 | Platform primitive | Trigger when unified search is required |
| 83 | Chatwoot × omnichannel conversations | 95 | 87 | God Source | Integrate next |
| 81 | Qdrant × permissioned vector retrieval | 94 | 86 | Platform primitive | Trigger with retrieval proof |
| 74 | Open Notebook × research and cited knowledge | 100 | 74 | God Source | Prove next |
| 74 | Metabase × governed business intelligence | 89 | 83 | God Source | Prove next |
| 74 | Listmonk × newsletter delivery | 95 | 78 | God Source candidate | Source-read, then growth pack |
| 73 | Teable × operational tables | 98 | 74 | God Source | Operate and harden |
| 73 | Cal.com × scheduling | 93 | 78 | God Source | Prove next |
| 73 | OpenFGA × cross-module authorization | 84 | 87 | Platform primitive | Trigger after one real grant model |
| 72 | Coolify × repeatable deployment control | 96 | 75 | God Source | Prove on supported Linux |
| 70 | Plane × projects and delivery host | 98 | 71 | God Source | Prove host |
| 70 | Documenso × contracts and signatures | 95 | 74 | God Source | Prove next |
| 69 | Keycloak × enterprise identity | 80 | 86 | Platform primitive | Enterprise trigger |
| 69 | docassemble × guided documents | 92 | 75 | God Source | Prove next |
| 66 | AFFiNE × documents and canvas | 94 | 70 | God Source | Operate and harden |
| 61 | OpenContracts × diligence intelligence | 84 | 73 | High-leverage specialist | Legal/industry trigger |
| 55 | ERPNext × finance/ERP edge cases | 86 | 64 | High-leverage specialist | Finance/client trigger |
| 53 | AionUI × agent workbench interface | 80 | 66 | High-leverage interface | Runtime spike |

Priority is `value × feasibility`, not a substitute for the proof gates. A lower-priority specialist may be the correct first move when an active client has that exact need.

## The actual God Source portfolio

The strongest complete capability sources in this tranche are:

- **Activepieces** — makes connectors and automations reusable across every client while giving agents controlled actions.
- **Chatwoot** — creates a shared conversation authority agents and humans can work against without rebuilding every communication channel.
- **Teable** — supplies a complete operational-data product rather than another hand-built table UI.
- **Plane** — supplies the work and delivery operating surface and remains the dominant-host candidate.
- **AFFiNE** — supplies the complete documents/canvas experience; the value is preserving the engine, not copying its visual ideas.
- **Open Notebook** — turns public and private source into cited research workflows and an agent-accessible knowledge plane.
- **Documenso** — supplies the legally meaningful signature engine and evidence trail.
- **SurveyJS** — gives SISO an unusually high-leverage permissive intake primitive without operating another full SaaS shell.
- **Metabase** — supplies governed internal and client-facing BI rather than rebuilding a reporting product.
- **Coolify** — turns deploy, environment, database and service operations into repeatable agency delivery infrastructure.
- **Cal.com and docassemble** — complete specialist slices that can become reusable scheduling and guided-document packs. **Listmonk** has the same value shape, but remains a candidate until a direct source read clears the evidence gate.

Meilisearch, Qdrant, Keycloak and OpenFGA score highly but are **platform primitives**, not standalone client value. AionUI is a high-value **interface**, but it does not own business data or actions; its value appears only when connected to the SISO capability gateway.

## What remains

The source universe is already present: 9,636 deduplicated repositories, including 7,942 business-software candidates. The next Foundry work is not another broad GitHub scrape. It is to apply this same row contract to the remaining high-signal candidates, starting with the existing source-read dossiers and the 707 pre-scored proof selections.

Every new row must identify:

1. the exact SISO business job and value mechanism;
2. the destination: internal stack, Agency Edition, client module, industry pack, infrastructure or reference;
3. the authority group, so overlapping products do not become parallel systems of record;
4. the human and agent operations it can expose;
5. the ownership/adoption route and license boundary;
6. gross value, feasibility and evidence maturity;
7. the next falsifiable proof gate; and
8. the owner that will turn evidence into a released capability.

No repository is promoted because it has stars. No score is permanent. Real deployments must feed cost saved, labour saved, revenue created, risk reduced and agent autonomy back into the matrix.
