// grade.mjs — the mechanical judge for the webhook-receiver slice.
// Imports the arm's webhook.mjs, drives it through happy + adversarial cases,
// asserts on REAL behavior (incl. a separate-process persistence re-open and
// a source-scan for the constant-time-compare contract). Emits one-line JSON.
//
// Usage: node grade.mjs <path-to-arm-webhook.mjs>
import crypto from 'node:crypto';
import { readFileSync, rmSync, existsSync, mkdtempSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const armPath = process.argv[2];
const SECRET = 'whsec_test_4f8a9d2c';
const schema = {
  type: 'object',
  properties: { event: { type: 'string' }, amount: { type: 'number' } },
  required: ['event', 'amount'],
  additionalProperties: true,
};

const sign = (raw) => 'sha256=' + crypto.createHmac('sha256', SECRET).update(raw).digest('hex');

const checks = {};
const fail = (msg) => { console.log(JSON.stringify({ working: false, where: msg, checks })); process.exit(0); };

const dir = mkdtempSync(join(tmpdir(), 'whrig-'));
const dbPath = join(dir, 'events.db');

let mod;
try { mod = await import(pathToFileURL(armPath).href); }
catch (e) { fail('import_failed: ' + e.message); }
if (typeof mod.createReceiver !== 'function') fail('no_createReceiver_export');

let rec;
try { rec = mod.createReceiver({ dbPath, secret: SECRET, schema }); }
catch (e) { fail('createReceiver_threw: ' + e.message); }
if (typeof rec.handle !== 'function') fail('no_handle');

const valid = JSON.stringify({ event: 'payment.succeeded', amount: 100 });

// --- 1. happy path: valid sig + valid body + fresh key -> accepted, has id
let r1;
try { r1 = await rec.handle({ rawBody: valid, signatureHeader: sign(valid), idempotencyKey: 'k-1' }); }
catch (e) { fail('handle_threw_happy: ' + e.message); }
checks.happy_accepted = r1 && r1.status === 200 && r1.reason === 'accepted' && r1.replayed === false && r1.id != null;
if (!checks.happy_accepted) fail('happy_path_wrong: ' + JSON.stringify(r1));

// --- 2. bad signature -> 401, and body must NOT have been persisted
let r2;
try { r2 = await rec.handle({ rawBody: valid, signatureHeader: 'sha256=' + 'deadbeef'.repeat(8), idempotencyKey: 'k-2' }); }
catch (e) { fail('handle_threw_badsig: ' + e.message); }
checks.badsig_401 = r2 && r2.status === 401 && r2.reason === 'bad_signature';
if (!checks.badsig_401) fail('badsig_not_rejected: ' + JSON.stringify(r2));

// --- 2b. THE LENGTH-MISMATCH TRAP: a short hex sig must be rejected, NOT crash.
//     A naive timingSafeEqual(a,b) throws "Input buffers must have the same length".
let r2b;
try { r2b = await rec.handle({ rawBody: valid, signatureHeader: 'sha256=abc123', idempotencyKey: 'k-2b' }); }
catch (e) { fail('CRASH_on_length_mismatch: ' + e.message); }  // <-- the subtle HMAC bug, caught
checks.lenmismatch_safe = r2b && r2b.status === 401;
if (!checks.lenmismatch_safe) fail('lenmismatch_not_401: ' + JSON.stringify(r2b));

// --- 3. valid sig but body fails schema -> 400
const badBody = JSON.stringify({ event: 'x' }); // missing required 'amount'
let r3;
try { r3 = await rec.handle({ rawBody: badBody, signatureHeader: sign(badBody), idempotencyKey: 'k-3' }); }
catch (e) { fail('handle_threw_badbody: ' + e.message); }
checks.badbody_400 = r3 && r3.status === 400 && r3.reason === 'invalid_body';
if (!checks.badbody_400) fail('badbody_not_rejected: ' + JSON.stringify(r3));

// --- 3b. invalid JSON -> 400 (not a crash)
let r3b;
try { r3b = await rec.handle({ rawBody: '{not json', signatureHeader: sign('{not json'), idempotencyKey: 'k-3b' }); }
catch (e) { fail('CRASH_on_bad_json: ' + e.message); }
checks.badjson_400 = r3b && r3b.status === 400;
if (!checks.badjson_400) fail('badjson_not_400: ' + JSON.stringify(r3b));

// --- 4. IDEMPOTENCY: replay k-1 -> duplicate, replayed:true, SAME id as r1
let r4;
try { r4 = await rec.handle({ rawBody: valid, signatureHeader: sign(valid), idempotencyKey: 'k-1' }); }
catch (e) { fail('handle_threw_replay: ' + e.message); }
checks.replay_duplicate = r4 && r4.status === 200 && r4.replayed === true;
checks.replay_same_id = r4 && String(r4.id) === String(r1.id);
if (!checks.replay_duplicate) fail('replay_not_flagged: ' + JSON.stringify(r4));
if (!checks.replay_same_id) fail('replay_id_mismatch: r1=' + r1.id + ' r4=' + r4.id);

// --- 5. CONSTANT-TIME CONTRACT: scan source for timingSafeEqual usage and
//     the absence of a `=== signature` / `== signature` direct hex compare.
//     (Behavioral timing is too noisy to assert; the contract is structural.)
const src = readFileSync(armPath, 'utf8');
// strip comments + strings so the scan reads CODE, not prose/comments
const code = src
  .replace(/\/\*[\s\S]*?\*\//g, ' ')     // block comments
  .replace(/(^|[^:])\/\/[^\n]*/g, '$1')  // line comments (avoid http://)
  .replace(/(['"`])(?:\\.|(?!\1).)*\1/g, '""'); // string literals
checks.uses_timing_safe = /timingSafeEqual/.test(code);
// flag ANY ==, ===, != , !== that has a digest/sig/hmac/mac/expected/computed/
// provided token on either side -> a non-constant-time hex/string equality compare.
// only the COMPUTED-digest tokens; input-name guards (typeof signature!=='string')
// and length guards (expected.length !== provided.length) are legitimate and must
// NOT trip the check. The bug we hunt is a VALUE equality of the digest itself,
// so require the token NOT be immediately followed by `.length`/`.byteLength`.
const SIGVAL = '(?:digest\\b|expected\\w*|computed\\w*|hmac\\w*|\\bmac\\b)(?!\\s*\\.\\s*(?:length|byteLength))';
const naiveCompare =
     new RegExp(SIGVAL + '\\s*[!=]==?\\s*', 'i').test(code) ||
     new RegExp('[!=]==?\\s*' + SIGVAL, 'i').test(code);
checks.no_naive_eq_compare = !naiveCompare;

// --- 6. SEPARATE-PROCESS PERSISTENCE: close, re-open the db file in a fresh
//     node process via better-sqlite3 (or sqlite3 cli) and confirm exactly one
//     row for k-1 survived (the happy insert), and k-2/k-2b/k-3/k-3b did NOT persist.
try { rec.close && rec.close(); } catch {}
checks.db_file_exists = existsSync(dbPath);
if (!checks.db_file_exists) fail('no_db_file');

// Re-open in a separate process. DRIVER-AGNOSTIC: try the Node 22 built-in
// node:sqlite first (always available, zero deps), then fall back to the arm's
// better-sqlite3. We don't know the table/columns the arm used, so we scan ALL
// user tables and assert: k-1 appears, the rejected keys do not. Fair to either
// persistence choice (built-in or npm driver).
const probe = `
function openRows(p) {
  try {
    const { DatabaseSync } = require('node:sqlite');
    const db = new DatabaseSync(p, { readOnly: true });
    const tabs = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all().map(t=>t.name);
    let blob=''; for (const t of tabs){ try{ blob += JSON.stringify(db.prepare('SELECT * FROM '+t).all()); }catch{} }
    db.close(); return blob;
  } catch (e1) {
    const Database = require('better-sqlite3');
    const db = new Database(p, { readonly: true });
    const tabs = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all().map(t=>t.name);
    let blob=''; for (const t of tabs){ try{ blob += JSON.stringify(db.prepare('SELECT * FROM '+t).all()); }catch{} }
    db.close(); return blob;
  }
}
const blob = openRows(${JSON.stringify(dbPath)});
const has = (k)=> blob.includes(k);
process.stdout.write(JSON.stringify({
  k1: has('k-1'), k2: has('k-2'), k2b: has('k-2b'), k3: has('k-3'), k3b: has('k-3b'),
  payment: blob.includes('payment.succeeded')
}));
`;
let persist;
try {
  // run with better-sqlite3 resolvable from the arm's own node_modules (cwd = arm dir)
  const out = execFileSync('node', ['-e', probe], { cwd: join(armPath, '..'), encoding: 'utf8' });
  persist = JSON.parse(out);
} catch (e) { fail('separate_process_reopen_failed: ' + (e.stderr || e.message)); }

checks.persisted_k1 = persist.k1 === true && persist.payment === true;
checks.did_not_persist_rejected = persist.k2 === false && persist.k2b === false && persist.k3 === false && persist.k3b === false;

// --- final
const ALL = [
  'happy_accepted','badsig_401','lenmismatch_safe','badbody_400','badjson_400',
  'replay_duplicate','replay_same_id','uses_timing_safe','no_naive_eq_compare',
  'db_file_exists','persisted_k1','did_not_persist_rejected'
];
const working = ALL.every(k => checks[k] === true);
try { rmSync(dir, { recursive: true, force: true }); } catch {}
console.log(JSON.stringify({ working, checks }));
