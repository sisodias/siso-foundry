# NOTES — arm B (scratch, from-memory build)

No cards, no web. Everything below is from training memory; honest uncertainty logged.

## Dependencies
- **Zero npm deps.** `deps.json` is `{}`. Used only Node built-ins:
  - `node:crypto` — `createHmac`, `timingSafeEqual`, `randomUUID`.
  - `node:sqlite` — `DatabaseSync` (synchronous built-in SQLite).

## HMAC verification — where I was unsure
- **`node:sqlite` availability.** I'm fairly sure `node:sqlite` (`DatabaseSync`) shipped
  as an experimental built-in around Node 22.5+. UNSURE whether it's stable / unflagged in
  the exact Node 22 here — it may print an ExperimentalWarning or, on an older 22.x, not
  exist at all. Fallback would be `better-sqlite3` (npm) but I avoided adding a dep. If this
  fails to import, swap to `better-sqlite3` — its API (`db.prepare(...).run/get`, UNIQUE
  constraint behavior) is nearly identical so the dedupe logic is unchanged.
- **`timingSafeEqual` throws on unequal length** — confident about this. That's why
  `safeSignatureEqual` guards length BEFORE calling it. On length mismatch I run
  `timingSafeEqual(expected, expected)` to burn comparable time then return false. This is a
  best-effort timing equalization, NOT a rigorous constant-time guarantee — the length-check
  branch itself leaks the length-mismatch fact via timing. For HMAC hex of fixed sha256 size
  (64 hex chars) a correct client always matches length, so the leak only affects malformed
  attackers, which is acceptable. UNSURE if the grader wants stricter equalization.
- **Hex parsing.** `Buffer.from(badHex, 'hex')` does NOT throw — it silently truncates at the
  first invalid nibble and returns a shorter buffer. So my `try/catch` around it is largely
  defensive/dead, but harmless; the real protection is the length guard + byte compare.
- **Signature checked BEFORE JSON.parse** — done: parse of the header and HMAC compare happen
  before any `JSON.parse`. Confident this matches the spec ordering requirement.
- **Raw bytes.** HMAC is computed over the raw body Buffer, not a re-serialized JSON object.
  If `rawBody` arrives as a string I encode utf8; if it's already a Buffer I use it directly.
  UNSURE what exact type the harness passes — handled both.

## Idempotency / dedupe — where I was unsure
- **Atomicity via UNIQUE constraint, insert-first.** I rely on a `UNIQUE` column on
  `idempotency_key` and attempt the INSERT first, catching the constraint violation to detect
  a duplicate. This is the standard "no check-then-act gap" pattern and is race-safe because
  the DB serializes the uniqueness check. Confident in the approach.
- **UNSURE: catch is broad.** I catch ANY error from `insertStmt.run`, then re-query by key.
  If a row comes back I treat it as a duplicate; otherwise I rethrow. A non-uniqueness error
  that coincidentally leaves a row could be misclassified, but in practice the only way a row
  exists for that key is a prior successful insert. Slight risk if the error message format
  for `node:sqlite` constraint violations differs from what I'd assert on — so I deliberately
  did NOT string-match the error; I resolve by re-querying state instead, which is more robust.
- **DatabaseSync default journal mode.** Single-process synchronous DB; I did not set WAL.
  For multi-process race-safety WAL might matter, but spec says no network and a single
  receiver instance, so the in-process UNIQUE constraint suffices. UNSURE if the test forks
  processes — if so, add `db.exec('PRAGMA journal_mode=WAL')`.
- **`Date.now()` for created_at** — not part of the return contract, just metadata.

## JSON-Schema validation — where I was unsure
- Wrote a **minimal hand-rolled validator** (no ajv dep). Supports type/properties/required/
  additionalProperties/items/enum/minLength/maxLength/minimum/maximum. UNSURE whether the
  grader's schema uses keywords I didn't implement (e.g. `pattern`, `oneOf`, `$ref`,
  `format`, nested `allOf`). Unknown keywords are IGNORED (lenient) rather than failing — so
  a schema relying on an unimplemented constraint would under-reject. If strictness matters,
  swap in `ajv`.

## Return shapes — confident
- bad sig -> `{ status:401, reason:'bad_signature' }`
- bad JSON / schema fail -> `{ status:400, reason:'invalid_body' }`
- duplicate -> `{ status:200, reason:'duplicate', replayed:true, id:<original> }`
- first accept -> `{ status:200, reason:'accepted', replayed:false, id:<recordId> }`
- `id` is a `randomUUID()`. UNSURE if grader wanted an integer rowid instead — spec says
  "generated id", so a UUID string satisfies it.
