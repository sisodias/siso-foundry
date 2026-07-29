// probe-rawbody.mjs <arm-webhook.mjs>
// The classic HMAC bug: verifying the signature against a RE-SERIALIZED body
// (JSON.parse -> JSON.stringify) instead of the RAW bytes. We sign a body with
// non-canonical whitespace + key order that would NOT survive a round-trip.
// A correct arm (HMAC over raw bytes) ACCEPTS it. A buggy arm that re-serializes
// before HMAC would compute a different digest and REJECT (401).
import crypto from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const armPath = process.argv[2];
const SECRET = 'whsec_test_4f8a9d2c';
const schema = { type:'object', properties:{ event:{type:'string'}, amount:{type:'number'} }, required:['event','amount'] };
// Non-canonical: extra spaces, newlines, amount-before-event. Valid JSON, but a
// re-serialization would change the bytes -> digest mismatch if HMAC'd post-parse.
const raw = '{\n  "amount":  100,\n    "event": "payment.succeeded"\n}';
const sign = (r) => 'sha256=' + crypto.createHmac('sha256', SECRET).update(r).digest('hex');

const dir = mkdtempSync(join(tmpdir(), 'whraw-'));
const mod = await import(pathToFileURL(armPath).href);
const rec = mod.createReceiver({ dbPath: join(dir, 'r.db'), secret: SECRET, schema });
const res = await rec.handle({ rawBody: raw, signatureHeader: sign(raw), idempotencyKey: 'raw-1' });
try { rec.close && rec.close(); } catch {}

const ok = res && res.status === 200; // correct: raw-bytes HMAC accepts the non-canonical body
console.log(JSON.stringify({
  raw_bytes_hmac: ok,
  verdict: ok ? 'CORRECT (HMAC over raw bytes — non-canonical body accepted)'
              : 'BUG (rejected a validly-signed non-canonical body — likely re-serializes before HMAC)',
  raw_result: res,
}));
