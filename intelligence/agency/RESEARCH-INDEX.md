# Foundry research: canonical project entry

Foundry owns these research records. The Great Library registers their exact
source version and generates human and machine reading surfaces. Projects should
cite the stable Foundry Work ID and pin the selected source revision when using
a record; a local copy does not become another canonical source.

- Work ID: `gls:work:ec664d93-df93-48c5-be40-5d0165886c01`
- Library entry: https://great-library-of-siso.pages.dev/works/siso-foundry/
- Industries: https://great-library-of-siso.pages.dev/industries/
- Code valuation: https://great-library-of-siso.pages.dev/valuation/
- Agent dossier: https://great-library-of-siso.pages.dev/works/siso-foundry/index.json

## Public research records

`industries/*.json` contains 17 industry records: process hypotheses, existing
software capabilities, repository candidates, source references and falsifiers.
The source observations are dated 5 September 2026. Research status, jurisdiction,
human authority, rights and missing-value fields must travel with each record.

`economics/observed-value-model.json` specifies the evidence and cash/capacity
formula. `economics/repo-value-inputs.json` has ten existing-repository examples.
Missing mandatory inputs produce null. The evidence score counts documented
gates; it is neither money nor a quality multiplier. The model's retained
`public_state` records its original preparation state; the Library Release and
source commit establish subsequent publication.

Library JSON endpoints are read-only projections over these exact source files,
with source URLs and SHA-256 receipts. They must not silently refresh the source
revision or turn null values into zero. Upstream code and data retain their own
licences; the Foundry MIT licence does not grant rights to third-party payloads.

## Project-scoped material

Internal review packets, source inventories and feed preparation also exist under
Foundry ownership. Their private source context is not part of this public
release. Authorized projects resolve the existing private Library overlay to the
Foundry checkout and its project resource directory. Do not infer public access
or copy those packets into public project documentation.

## Verification boundary

The scoped industry/value checks pass. Full `npm test` still stops on the
pre-existing external `lane-b-capability-atlas.jsonl` input; source publication
does not resolve that missing asset or claim a green application suite.
