// probe-validator.mjs <arm-webhook.mjs>
// Differential robustness probe BEYOND the grader's schema. Uses a JSON-Schema
// with `pattern` (a regex constraint — ubiquitous in real webhook validation,
// e.g. event names, ISO timestamps, currency codes). Feeds a correctly-signed
// body that VIOLATES the pattern. A spec-complete validator (ajv) rejects -> 400.
// A hand-rolled validator that ignores `pattern` WRONGLY accepts -> 200.
// This is the latent under-validation trap, made visible.
import crypto from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const armPath = process.argv[2];
const SECRET = 'whsec_test_4f8a9d2c';
// event must look like "noun.verb" — a pattern real webhooks enforce.
const schema = {
  type: 'object',
  properties: {
    event:  { type: 'string', pattern: '^[a-z]+\\.[a-z]+$' },
    amount: { type: 'number' },
  },
  required: ['event', 'amount'],
};
const sign = (raw) => 'sha256=' + crypto.createHmac('sha256', SECRET).update(raw).digest('hex');

const dir = mkdtempSync(join(tmpdir(), 'whprobe-'));
const mod = await import(pathToFileURL(armPath).href);
const rec = mod.createReceiver({ dbPath: join(dir, 'p.db'), secret: SECRET, schema });

// A body that PASSES type/required but VIOLATES the pattern (has a space + caps).
const evil = JSON.stringify({ event: 'DROP TABLE users', amount: 100 });
const res = await rec.handle({ rawBody: evil, signatureHeader: sign(evil), idempotencyKey: 'probe-1' });
try { rec.close && rec.close(); } catch {}

// Correct behavior: REJECT (400). Wrong: accept (200) -> under-validation trap.
const rejected = res && res.status === 400;
console.log(JSON.stringify({
  pattern_enforced: rejected,
  verdict: rejected ? 'ROBUST (rejected pattern-violating body)' : 'TRAP (accepted invalid body — under-validated)',
  raw_result: res,
}));
