# SPEC — Webhook Receiver (the harder slice)

Build an ES module `webhook.mjs` exporting **one** async function:

```js
export function createReceiver({ dbPath, secret, schema }) { ... }
// returns: { handle, close }
```

`handle({ rawBody, signatureHeader, idempotencyKey })` must:

1. **VERIFY HMAC** — `signatureHeader` is of the form `sha256=<hex>`. Compute
   HMAC-SHA256 of the **raw request body bytes** (NOT a re-serialized object)
   keyed by `secret`. If it does not match, return `{ status: 401, reason: 'bad_signature' }`.
   The comparison MUST be constant-time and MUST NOT throw on a length mismatch.

2. **VALIDATE BODY** — parse `rawBody` as JSON, then validate against `schema`
   (a JSON-Schema object passed in). On invalid JSON or schema failure, return
   `{ status: 400, reason: 'invalid_body' }`. (Order: signature is checked BEFORE
   parsing — never trust the body before the signature.)

3. **DEDUPE by idempotency key** — if `idempotencyKey` has been seen before,
   do NOT persist again; return `{ status: 200, reason: 'duplicate', replayed: true }`
   with the SAME stored record id as the original. Must be race-safe (atomic
   insert-or-detect, no check-then-act gap).

4. **PERSIST** — on first valid delivery, store the event (idempotency key,
   raw body, a generated record id) durably in SQLite at `dbPath`. Return
   `{ status: 200, reason: 'accepted', replayed: false, id: <recordId> }`.

`close()` closes the DB handle.

Constraints: ES module, Node 22, no network. The four capabilities are HMAC
verification, JSON-Schema validation, idempotent dedup, and SQLite persistence.
