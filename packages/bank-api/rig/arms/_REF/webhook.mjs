// _REF — a known-CORRECT reference. Used only to confirm the grader accepts
// correct code (calibration), not part of the experiment arms.
import crypto from 'node:crypto';
import Database from 'better-sqlite3';
import Ajv from 'ajv';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

export function createReceiver({ dbPath, secret, schema }) {
  mkdirSync(dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.exec(`CREATE TABLE IF NOT EXISTS events (
    idempotency_key TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    raw_body TEXT NOT NULL,
    created_at TEXT NOT NULL
  )`);
  const ajv = new Ajv();
  const validate = ajv.compile(schema);
  const insert = db.prepare(
    `INSERT OR IGNORE INTO events (idempotency_key, record_id, raw_body, created_at) VALUES (?,?,?,?)`
  );
  const getByKey = db.prepare(`SELECT record_id FROM events WHERE idempotency_key = ?`);

  function verifySig(rawBody, signatureHeader) {
    if (typeof signatureHeader !== 'string' || !signatureHeader.startsWith('sha256=')) return false;
    const provided = signatureHeader.slice('sha256='.length);
    const expected = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
    const a = Buffer.from(provided, 'hex');
    const b = Buffer.from(expected, 'hex');
    if (a.length !== b.length) return false;            // guard: timingSafeEqual throws on len mismatch
    return crypto.timingSafeEqual(a, b);
  }

  function handle({ rawBody, signatureHeader, idempotencyKey }) {
    if (!verifySig(rawBody, signatureHeader)) return { status: 401, reason: 'bad_signature' };
    let parsed;
    try { parsed = JSON.parse(rawBody); } catch { return { status: 400, reason: 'invalid_body' }; }
    if (!validate(parsed)) return { status: 400, reason: 'invalid_body' };

    const recordId = crypto.randomUUID();
    const res = insert.run(idempotencyKey, recordId, rawBody, new Date().toISOString());
    if (res.changes === 0) {
      const prior = getByKey.get(idempotencyKey);
      return { status: 200, reason: 'duplicate', replayed: true, id: prior.record_id };
    }
    return { status: 200, reason: 'accepted', replayed: false, id: recordId };
  }

  return { handle, close: () => db.close() };
}
