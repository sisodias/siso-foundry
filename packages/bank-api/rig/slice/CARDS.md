# THE BANK SLICE for this task (what Foundry actually returns)

You queried the Foundry bank for the capabilities this task needs. The bank
returned the following. This is ALL you get. You may NOT read source, READMEs,
npm, or the web. Wire from these cards + your Node-builtin knowledge only.

## Capability: JSON-Schema validation  — FULL CARD
- lib: **ajv** (`ajv-validator/ajv`), MIT, ship-OK, surface: medium
- provides: JSON Schema draft-07/2019-09/2020-12 validation; schema -> compiled
  validate() function (fast); detailed error reporting.
- recipe.install: `npm install ajv`
- recipe.wire:
  - `import Ajv from 'ajv'`
  - `const ajv = new Ajv()`
  - `const validate = ajv.compile({ type:'object', properties:{ n:{type:'string'} }, required:['n'] })`
  - `const ok = validate({ n:'x' })  // boolean; errors on validate.errors`
- smoke: `node --input-type=module -e "import Ajv from 'ajv'; const a=new Ajv(); const v=a.compile({type:'object',properties:{n:{type:'string'}},required:['n']}); if(v({n:'x'})&&!v({})){console.log('OK')}"`

## Capability: SQLite persistence  — FULL CARD
- lib: **better-sqlite3** (`WiseLibs/better-sqlite3`), MIT, ship-OK, surface: small
- provides: synchronous (no-callback) SQLite queries; prepared statements
  (.prepare/.get/.all/.run); transactions, WAL; embedded zero-config local DB.
- recipe.install: `npm install better-sqlite3`
- recipe.wire:
  - `import Database from 'better-sqlite3'`
  - `const db = new Database('app.db')`
  - `db.exec('CREATE TABLE IF NOT EXISTS t(x)')`
  - `db.prepare('INSERT INTO t(x) VALUES (?)').run(1)`
  - `const row = db.prepare('SELECT x FROM t').get()`

## Capability: HMAC signature verification  — SELECT-ONLY (no wire card exists)
The bank has NO contract card for this. SELECT returned these repos as the
"right libraries to reach for" (this is the bank's SELECT value — offline lib
steering), but with NO wiring recipe:
- `Caligatio/jsSHA` (TS, BSD-3, 2.3k★) — full SHA family + HMAC.
- `h2non/jshashes` (JS, BSD-3, 725★) — dependency-free hashing incl. HMAC.
- SELECT note: "Node ships `node:crypto` (createHmac) built-in — prefer it for
  HMAC-SHA256 unless you need browser support."
You must WIRE the HMAC verification yourself. No recipe is provided.

## Capability: idempotency / dedupe-by-key  — NOT IN BANK
SELECT returned ZERO results. The bank has no card and no repo for this
capability. You must implement it yourself from first principles.
