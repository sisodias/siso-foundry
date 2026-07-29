// webhook.mjs — HMAC-verified, schema-validated, idempotent webhook receiver.
// Node 22, ES module, no network. Uses node:crypto + node:sqlite (built-in).
//
// Public API:
//   createReceiver({ dbPath, secret, schema }) -> { handle, close }
//   handle({ rawBody, signatureHeader, idempotencyKey }) -> result object
//   close() -> closes the DB

import { createHmac, timingSafeEqual, randomUUID } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';

/**
 * Constant-time hex-signature compare that never throws on length mismatch.
 * timingSafeEqual REQUIRES equal-length buffers (it throws otherwise), so we
 * guard the length first. A length mismatch is an automatic non-match, but we
 * still run a timingSafeEqual against a self-buffer to keep timing uniform-ish.
 */
function safeSignatureEqual(expectedHex, providedHex) {
  // Normalize to Buffers from hex. Invalid hex -> empty/partial buffer; we
  // compare byte buffers so malformed input simply fails to match.
  let expected;
  let provided;
  try {
    expected = Buffer.from(expectedHex, 'hex');
    provided = Buffer.from(providedHex, 'hex');
  } catch {
    return false;
  }
  if (expected.length !== provided.length) {
    // Constant-ish: compare expected against itself so we still spend the time,
    // then return false. Avoids throwing and avoids an early-out on length.
    timingSafeEqual(expected, expected);
    return false;
  }
  return timingSafeEqual(expected, provided);
}

/**
 * Parse "sha256=<hex>" -> hex string, or null if shape is wrong.
 */
function parseSignatureHeader(signatureHeader) {
  if (typeof signatureHeader !== 'string') return null;
  const prefix = 'sha256=';
  if (!signatureHeader.startsWith(prefix)) return null;
  const hex = signatureHeader.slice(prefix.length);
  if (hex.length === 0) return null;
  return hex;
}

/**
 * Minimal JSON-Schema validator. Supports the common subset:
 *   type (object/array/string/number/integer/boolean/null),
 *   properties, required, additionalProperties, items,
 *   enum, minLength, maxLength, minimum, maximum.
 * Returns true/false. Intentionally lenient on unknown keywords (ignored).
 */
function validateSchema(value, schema) {
  if (schema == null || typeof schema !== 'object') return true; // no schema => accept

  const types = schema.type
    ? (Array.isArray(schema.type) ? schema.type : [schema.type])
    : null;

  if (types && !types.some((t) => matchesType(value, t))) return false;

  if (schema.enum && !schema.enum.some((e) => deepEqual(e, value))) return false;

  if (typeof value === 'string') {
    if (typeof schema.minLength === 'number' && value.length < schema.minLength) return false;
    if (typeof schema.maxLength === 'number' && value.length > schema.maxLength) return false;
  }

  if (typeof value === 'number') {
    if (typeof schema.minimum === 'number' && value < schema.minimum) return false;
    if (typeof schema.maximum === 'number' && value > schema.maximum) return false;
  }

  if (matchesType(value, 'object') && value !== null) {
    const props = schema.properties || {};
    if (Array.isArray(schema.required)) {
      for (const key of schema.required) {
        if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
      }
    }
    for (const [key, sub] of Object.entries(props)) {
      if (Object.prototype.hasOwnProperty.call(value, key)) {
        if (!validateSchema(value[key], sub)) return false;
      }
    }
    if (schema.additionalProperties === false) {
      const allowed = new Set(Object.keys(props));
      for (const key of Object.keys(value)) {
        if (!allowed.has(key)) return false;
      }
    } else if (schema.additionalProperties && typeof schema.additionalProperties === 'object') {
      const allowed = new Set(Object.keys(props));
      for (const key of Object.keys(value)) {
        if (!allowed.has(key) && !validateSchema(value[key], schema.additionalProperties)) return false;
      }
    }
  }

  if (Array.isArray(value) && schema.items) {
    for (const item of value) {
      if (!validateSchema(item, schema.items)) return false;
    }
  }

  return true;
}

function matchesType(value, type) {
  switch (type) {
    case 'object': return value !== null && typeof value === 'object' && !Array.isArray(value);
    case 'array': return Array.isArray(value);
    case 'string': return typeof value === 'string';
    case 'number': return typeof value === 'number' && !Number.isNaN(value);
    case 'integer': return typeof value === 'number' && Number.isInteger(value);
    case 'boolean': return typeof value === 'boolean';
    case 'null': return value === null;
    default: return true; // unknown type keyword => don't block
  }
}

function deepEqual(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a && b && typeof a === 'object') {
    const ak = Object.keys(a);
    const bk = Object.keys(b);
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    if (ak.length !== bk.length) return false;
    return ak.every((k) => deepEqual(a[k], b[k]));
  }
  return false;
}

export function createReceiver({ dbPath, secret, schema }) {
  const db = new DatabaseSync(dbPath);

  // Durable storage. idempotency_key is UNIQUE so the INSERT is the atomic
  // dedupe primitive: no check-then-act gap — we let the DB enforce it.
  db.exec(`
    CREATE TABLE IF NOT EXISTS deliveries (
      id              TEXT PRIMARY KEY,
      idempotency_key TEXT NOT NULL UNIQUE,
      raw_body        TEXT NOT NULL,
      created_at      INTEGER NOT NULL
    );
  `);

  const insertStmt = db.prepare(
    'INSERT INTO deliveries (id, idempotency_key, raw_body, created_at) VALUES (?, ?, ?, ?)'
  );
  const selectByKeyStmt = db.prepare(
    'SELECT id FROM deliveries WHERE idempotency_key = ?'
  );

  // HMAC key buffer. Treat secret as utf8 if string, pass through if Buffer.
  const keyBuf = Buffer.isBuffer(secret) ? secret : Buffer.from(String(secret), 'utf8');

  function handle({ rawBody, signatureHeader, idempotencyKey }) {
    // Normalize body to a Buffer of the RAW bytes. HMAC must be over raw bytes.
    const bodyBuf = Buffer.isBuffer(rawBody)
      ? rawBody
      : Buffer.from(typeof rawBody === 'string' ? rawBody : String(rawBody ?? ''), 'utf8');

    // 1) VERIFY HMAC (before any parsing).
    const providedHex = parseSignatureHeader(signatureHeader);
    if (providedHex === null) {
      return { status: 401, reason: 'bad_signature' };
    }
    const expectedHex = createHmac('sha256', keyBuf).update(bodyBuf).digest('hex');
    if (!safeSignatureEqual(expectedHex, providedHex)) {
      return { status: 401, reason: 'bad_signature' };
    }

    // 2) VALIDATE: parse JSON then schema-check.
    let parsed;
    try {
      parsed = JSON.parse(bodyBuf.toString('utf8'));
    } catch {
      return { status: 400, reason: 'invalid_body' };
    }
    if (!validateSchema(parsed, schema)) {
      return { status: 400, reason: 'invalid_body' };
    }

    // 3 + 4) DEDUPE + PERSIST atomically.
    // Strategy: attempt the INSERT first. The UNIQUE constraint on
    // idempotency_key makes this race-safe — exactly one INSERT wins; any
    // concurrent duplicate gets a constraint violation and we treat it as a
    // replay. No check-then-act gap.
    const newId = randomUUID();
    const rawStr = bodyBuf.toString('utf8');
    try {
      insertStmt.run(newId, String(idempotencyKey), rawStr, Date.now());
      return { status: 200, reason: 'accepted', replayed: false, id: newId };
    } catch (err) {
      // Unique violation => already delivered. Fetch the original id.
      const existing = selectByKeyStmt.get(String(idempotencyKey));
      if (existing && existing.id != null) {
        return { status: 200, reason: 'duplicate', replayed: true, id: existing.id };
      }
      // Not a uniqueness collision we can resolve — rethrow so it's visible.
      throw err;
    }
  }

  function close() {
    db.close();
  }

  return { handle, close };
}
