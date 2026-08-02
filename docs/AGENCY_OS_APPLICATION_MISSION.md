# Foundry business-application mission

Foundry's economic job is to discover valuable public source, determine what real business work it can improve, and route the evidence to the right SISO product or knowledge surface.

It is not a leaderboard of popular repositories and it does not automatically import code into a product. A repository is useful only when Foundry can connect it to a named business job, prove the relevant capability, and state a safe adoption route.

## The operating loop

```text
business job or industry constraint
  -> Foundry discovery and identity
  -> direct source, maintenance, rights and deployment evidence
  -> business-application decision
  -> Agency OS core / optional module / industry pack / managed service / pattern / reject
  -> client and internal operating evidence
  -> Great Library industry guidance
  -> refreshed Foundry demand and evaluation
```

The loop starts with demand, not supply. A 10,000-star repository receives early attention because it has broad adoption signal; stars are never proof of business value, source quality, maintainability, security, rights, or fit.

## System boundaries

| System | Owns | Does not own |
|---|---|---|
| **SISO Foundry** | Source identity, observations, discovery campaigns, evidence, reuse evaluation, business-application routing, and refresh signals | Client operations, product runtime, or automatic code promotion |
| **SISO Agency OS** | The agent-first business control plane, common object/capability contracts, product modules, industry packs, deployment templates, and managed operations | The universal source corpus or public research record |
| **SISO Knowledge** | Durable source corpus, provenance, indexes, graphs, and retrieval | Product selection or client execution |
| **SISO Evidence Engines** | Source-grounded claims, comparisons, counter-evidence, and decision packets | Stable Work identity or application runtime |
| **The Great Library of SISO** | Public, stable industry intelligence, accepted Works, answer lineage, contribution paths, and release history | Raw Foundry payloads, private client data, or unreviewed product claims |
| **Client and SISO deployments** | Real workflows, configured modules, permissions, operational data, and outcome evidence | Canonical research or cross-client data pooling |

Foundry may recommend a product route. Agency OS owns the product decision and implementation. The Great Library publishes only evidence-safe, rights-safe, non-client-specific projections.

## Agency OS pillars

Every candidate maps to one or more stable business pillars. Industry packs add domain objects, language, workflows, integrations, controls, and templates on top; they do not create a separate platform architecture.

1. **Revenue and relationships** — CRM, accounts, opportunities, proposals, pipeline, and retention.
2. **Work and delivery** — projects, tasks, resources, time, quality, and client delivery.
3. **Knowledge and research** — documents, notes, search, retrieval, citations, and institutional memory.
4. **Communication and support** — email, inboxes, chat, meetings, tickets, and notifications.
5. **Marketing and growth** — content, campaigns, forms, attribution, audiences, and experiments.
6. **Legal and trust** — contracts, signatures, approvals, compliance, consent, and evidence.
7. **Finance and administration** — quoting, billing, expenses, accounting, procurement, and reporting.
8. **Data and intelligence** — operational tables, analytics, BI, forecasting, and decision support.
9. **Automation and agents** — workflows, agent tools, action gateways, evaluation, and observability.
10. **Identity, security and governance** — tenancy, authentication, permissions, secrets, audit, and policy.
11. **Files, media and content** — storage, asset management, publishing, and content delivery.
12. **Deployment and operations** — hosting, databases, queues, backups, upgrades, monitoring, and recovery.

The machine-readable pillar, route, and evaluation vocabulary is [`agency-os-routing-contract.json`](../packages/business-application/agency-os-routing-contract.json).

## Application routes

A reviewed repository receives exactly one primary route for a stated context:

| Route | Meaning |
|---|---|
| `agency_os_core` | A common capability that belongs in every serious Agency OS distribution. |
| `optional_module` | A source-owned application or coherent module enabled when a business needs it. |
| `managed_service` | Operated beside Agency OS and accessed through a governed adapter or deep link. |
| `connector_only` | Keep the external or client-owned system; expose its data/actions through the capability gateway. |
| `infrastructure_primitive` | Search, storage, identity, queues, databases, hosting, or another runtime substrate. |
| `industry_pack` | Domain-specific workflows, objects, compliance, templates, or integrations layered on the common base. |
| `pattern_reference` | Learn from a bounded architecture, interaction, schema, or workflow without adopting the application. |
| `client_specific` | Valuable for a named engagement but not yet justified as reusable Agency OS product. |
| `watchlist` | Plausible value, but evidence, timing, maintenance, rights, or overlap blocks promotion. |
| `reject` | Irrelevant, unsafe, unmaintained, duplicative, uneconomic, or otherwise unsuitable. |

An adoption route also declares the ownership path: integrate upstream, operate a pinned service, maintain a source-owned fork, extract a licensed module, implement a clean-room pattern, or build a native replacement. “Found on GitHub” is not an ownership strategy.

## Evaluation gate

Promotion requires evidence for all of these questions:

1. What business job changes, for whom, and in which pillar or industry?
2. What exact source paths, behavior, API, data model, or runnable surface prove the capability?
3. Does it replace spend, compress labour, increase revenue, reduce risk, or unlock an agent action?
4. Can humans and agents access it through `discover`, `read`, `search`, `write`, `action`, `subscribe`, `approve`, and `audit`, with absences explicit?
5. What owns the data, how is tenancy enforced, and can the data be exported, deleted, backed up, and restored?
6. What are the license, trademark, source-offer, attribution, privacy, and redistribution boundaries?
7. Is the project maintained and operationally supportable? What is the upgrade and rollback path?
8. What existing Agency OS capability does it overlap, and why is this addition better than extending the incumbent?
9. Is the best outcome core, optional, industry-specific, managed, connected, learned from, watched, or rejected?

No candidate becomes product truth until direct source review and the relevant product proof gates pass.

## Industry Library projection

The Great Library can expose an **Industries Library** as a public projection over accepted evidence. Each industry dossier should answer:

- how the industry makes money and where work, delay, risk, and information loss occur;
- the important actors, objects, workflows, controls, and integrations;
- which Agency OS pillars are universal and which additions form the industry pack;
- source-backed repository candidates and their application routes;
- what agents can safely read, decide, draft, or execute;
- expected value mechanisms and the evidence grade behind them;
- implementation readiness: `research`, `validated`, `packaged`, `deployed`, or `proven`;
- contribution gaps and refresh triggers.

People may contribute public repository locators, source evidence, corrections, and industry workflows. Code enters a SISO product only through its original license/provenance and the promotion gate; the Library does not flatten third-party repositories into itself.

This lets SISO accumulate option value before choosing an industry. When a client arrives, the Agency can start from an existing dossier and candidate pack, validate it against the client's real workflow, and promote only what survives contact with operations.

## Discovery program

The first business-application program uses three inputs in order:

1. the existing Foundry identity corpus and preserved 10,000+ star slice for broad recall;
2. the existing 100+ star business-software universe campaign for category and long-tail coverage; and
3. focused GitHub gap campaigns for missing pillars, industry needs, or material refreshes.

The public [`agency-business-software-v1`](../pipelines/github/campaigns/agency-business-software-v1.json) contract is a reproducible high-signal refresh, not a claim to enumerate GitHub through a single search page. The large existing corpus remains the correct starting point.

## Success measure

Foundry succeeds when it reduces the time from “this business has a valuable problem” to an evidence-backed build, integration, managed-service, or rejection decision—and when the resulting knowledge can be reused without leaking client data or repeating the research.
