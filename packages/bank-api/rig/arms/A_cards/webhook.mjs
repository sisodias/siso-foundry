import { createHmac, timingSafeEqual, randomUUID } from 'node:crypto';
import Database from 'better-sqlite3';
import Ajv from 'ajv';

export function createReceiver({ dbPath, secret, schema }) {
  const ajv = new Ajv();
  const validate = ajv.compile(schema);

  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.exec(`
    CREATE TABLE IF NOT EXISTS deliveries (
      idempotency_key TEXT PRIMARY KEY,
      raw_body        TEXT NOT NULL,
      id              TEXT NOT NULL
    )
  `);

  const insertStmt = db.prepare(
    'INSERT OR IGNORE INTO deliveries (idempotency_key, raw_body, id) VALUES (?, ?, ?)'
  );
  const selectStmt = db.prepare(
    'SELECT id FROM deliveries WHERE idempotency_key = ?'
  );

  function verifySignature(rawBody, signatureHeader) {
    // signatureHeader is "sha256=<hex>"
    if (typeof signatureHeader !== 'string') return false;
    const prefix = 'sha256=';
    if (!signatureHeader.startsWith(prefix)) return false;
    const providedHex = signatureHeader.slice(prefix.length);

    // Normalize rawBody to a Buffer of the RAW bytes.
    const bodyBuf = Buffer.isBuffer(rawBody)
      ? rawBody
      : Buffer.from(rawBody, 'utf8');

    const expected = createHmac('sha256', secret).update(bodyBuf).digest();

    // Parse provided hex into bytes. Bad hex -> empty/odd buffer; treat as mismatch.
    let provided;
    try {
      provided = Buffer.from(providedHex, 'hex');
    } catch {
      return false;
    }

    // Constant-time compare that MUST NOT throw on length mismatch.
    // timingSafeEqual throws if lengths differ, so guard length first.
    if (provided.length !== expected.length) return false;
    return timingSafeEqual(provided, expected);
  }

  function handle({ rawBody, signatureHeader, idempotencyKey }) {
    // 1. VERIFY HMAC (before parsing).
    if (!verifySignature(rawBody, signatureHeader)) {
      return { status: 401, reason: 'bad_signature' };
    }

    // 2. VALIDATE: parse JSON then schema.
    const bodyStr = Buffer.isBuffer(rawBody) ? rawBody.toString('utf8') : String(rawBody);
    let parsed;
    try {
      parsed = JSON.parse(bodyStr);
    } catch {
      return { status: 400, reason: 'invalid_body' };
    }
    if (!validate(parsed)) {
      return { status: 400, reason: 'invalid_body' };
    }

    // 3 + 4. DEDUPE + PERSIST atomically.
    // INSERT OR IGNORE is a single atomic statement: no check-then-act gap.
    // The PRIMARY KEY on idempotency_key enforces uniqueness; a concurrent
    // duplicate either inserts (changes=1) or is ignored (changes=0).
    const newId = randomUUID();
    const info = insertStmt.run(idempotencyKey, bodyStr, newId);

    if (info.changes === 0) {
      // Already seen: do NOT persist again. Return the ORIGINAL id.
      const existing = selectStmt.get(idempotencyKey);
      return {
        status: 200,
        reason: 'duplicate',
        replayed: true,
        id: existing.id,
      };
    }

    // First valid delivery persisted.
    return {
      status: 200,
      reason: 'accepted',
      replayed: false,
      id: newId,
    };
  }

  function close() {
    db.close();
  }

  return { handle, close };
}
