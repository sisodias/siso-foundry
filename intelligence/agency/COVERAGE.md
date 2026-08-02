# Agency OS coverage inventory

Deterministic output from the Agency OS expansion receipts. The 497 candidate application rows are repository × use-case rows; the inventory below deduplicates them with Lane B capability-atlas references. Inferred evidence is never counted as verified.

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
| `revenue_relationships` | 86 | adversarial-confirmed: 1, inferred: 14, metadata: 68, source-read: 3 |
| `work_delivery` | 87 | inferred: 7, metadata: 77, source-read: 3 |
| `knowledge_research` | 61 | inferred: 19, metadata: 37, source-read: 5 |
| `communication_support` | 88 | adversarial-confirmed: 2, inferred: 26, metadata: 52, source-read: 8 |
| `marketing_growth` | 42 | adversarial-confirmed: 4, inferred: 6, metadata: 20, source-read: 12 |
| `legal_trust` | 35 | inferred: 19, metadata: 15, source-read: 1 |
| `finance_administration` | 57 | adversarial-confirmed: 3, inferred: 5, metadata: 47, source-read: 2 |
| `data_intelligence` | 100 | adversarial-confirmed: 1, inferred: 40, metadata: 33, source-read: 26 |
| `automation_agents` | 94 | adversarial-confirmed: 4, inferred: 37, metadata: 30, source-read: 23 |
| `identity_security_governance` | 29 | inferred: 8, metadata: 13, source-read: 8 |
| `files_media_content` | 80 | adversarial-confirmed: 2, inferred: 24, metadata: 49, source-read: 5 |
| `deployment_operations` | 64 | adversarial-confirmed: 1, inferred: 31, metadata: 23, source-read: 9 |

## Evidence grades

- `adversarial-confirmed`: 10
- `inferred`: 131
- `metadata`: 408
- `source-read`: 79

The machine-readable row-level inventory is [`coverage-inventory.json`](coverage-inventory.json). Each row includes canonical verticals, preserved raw labels, categories, analyzed flags, license/reuse fields, and hashed source-artifact receipts.
