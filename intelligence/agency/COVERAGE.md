# Agency OS coverage inventory

Deterministic output from the Agency OS expansion receipts. The 497 candidate application rows are repository × use-case rows; the inventory below deduplicates them with Lane B capability-atlas references. Inferred evidence is never counted as verified. Lane-B routing uses the explicit job-based `capability-pillar-map.json`: raw slice names are provenance only, and a project receives only the mapped pillars of the capabilities that reference it.

## Definitions

- **Analyzed:** a repository has a source-read or adversarial receipt in the supplied artifacts.
- **Verified:** only an adversarial-confirmed verifier verdict; metadata and inferred rows never qualify.
- **Reusable:** a repository has reusable analysis fields and source-read or adversarial evidence; this does not grant reuse rights.

## Aggregate coverage

| Measure | Count | Percent of unique repositories |
|---|---:|---:|
| Unique repositories/projects | 628 | 100% |
| Source-read or adversarial-confirmed | 89 | 14.17% |
| Adversarial-confirmed | 10 | 1.59% |
| Reusable analysis (source-read/confirmed, at least one analysis receipt) | 89 | 14.17% |

Application rows: **497**. Frontier rows: **30**. Capability-atlas rows: **189**. Unmapped labels: **0**.

## Canonical vertical coverage

| Canonical pillar | Projects | Evidence split |
|---|---:|---|
| `revenue_relationships` | 89 | adversarial-confirmed: 1, inferred: 16, metadata: 68, source-read: 4 |
| `work_delivery` | 91 | inferred: 11, metadata: 77, source-read: 3 |
| `knowledge_research` | 66 | adversarial-confirmed: 1, inferred: 23, metadata: 37, source-read: 5 |
| `communication_support` | 96 | adversarial-confirmed: 2, inferred: 32, metadata: 53, source-read: 9 |
| `marketing_growth` | 45 | adversarial-confirmed: 4, inferred: 7, metadata: 21, source-read: 13 |
| `legal_trust` | 19 | inferred: 8, metadata: 6, source-read: 5 |
| `finance_administration` | 67 | adversarial-confirmed: 3, inferred: 11, metadata: 50, source-read: 3 |
| `data_intelligence` | 105 | adversarial-confirmed: 1, inferred: 44, metadata: 34, source-read: 26 |
| `automation_agents` | 86 | adversarial-confirmed: 2, inferred: 33, metadata: 28, source-read: 23 |
| `identity_security_governance` | 42 | inferred: 20, metadata: 14, source-read: 8 |
| `files_media_content` | 49 | inferred: 10, metadata: 36, source-read: 3 |
| `deployment_operations` | 42 | inferred: 13, metadata: 23, source-read: 6 |

## Evidence grades

- `adversarial-confirmed`: 10
- `inferred`: 131
- `metadata`: 408
- `source-read`: 79

The machine-readable row-level inventory is [`coverage-inventory.json`](coverage-inventory.json). Each row includes canonical verticals, preserved raw labels, categories, analyzed flags, license/reuse fields, and hashed source-artifact receipts.
