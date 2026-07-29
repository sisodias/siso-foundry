// _NEG — deliberately broken WITH THE EXACT SUBTLE BUGS this slice hunts:
//   (1) naive === compare of hex digests (not constant-time)
//   (2) timingSafeEqual would also crash on length mismatch, so this uses ===
//       which is the most common real-world mistake. Grader must REJECT this.
// Used only to confirm the grader rejects the subtle-bug code (calibration).
import crypto from 'node:crypto';
import Database from 'better-sqlite3';
import Ajv from 'ajv';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

export function createReceiver({ dbPath, secret, schema }) {
  mkdirSync(dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  db.exec(`CREATE TABLE IF NOT EXISTS events (id TEXT, k TEXT, body TEXT)`);
  const ajv = new Ajv();
  const validate = ajv.compile(schema);

  function handle({ rawBody, signatureHeader, idempotencyKey }) {
    const provided = (signatureHeader || '').replace('sha256=', '');
    const expected = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
    // BUG: timing-unsafe direct equality of the digest
    if (provided !== expected) return { status: 401, reason: 'bad_signature' };
    let parsed;
    try { parsed = JSON.parse(rawBody); } catch { return { status: 400, reason: 'invalid_body' }; }
    if (!validate(parsed)) return { status: 400, reason: 'invalid_body' };
    const id = crypto.randomUUID();
    db.prepare('INSERT INTO events VALUES (?,?,?)').run(id, idempotencyKey, rawBody);
    return { status: 200, reason: 'accepted', replayed: false, id };
  }
  return { handle, close: () => db.close() };
}
