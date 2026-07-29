# NOTES — arm A (CARDS-ONLY)

Where the cards were thin and I had to guess / fill in from Node-builtin knowledge.

## HMAC signature verification (SELECT-only, no wiring recipe)
The card only pointed at libs + noted "prefer node:crypto createHmac". Everything below the wiring level was my own:

- **Chose `node:crypto` over jsSHA/jshashes** per the SELECT note (no browser need). No card told me the API shape; used `createHmac('sha256', secret).update(body).digest()` from memory.
- **Raw-bytes handling**: spec says HMAC over the RAW body bytes. The card said nothing about whether `rawBody` arrives as a Buffer or string. Guessed it may be either, so I normalize: pass a Buffer straight through, else `Buffer.from(str, 'utf8')`. If the caller sends a string that was decoded with a non-utf8 charset, this would mismatch — assumed utf8.
- **Header format parsing**: spec gives `"sha256=<hex>"`. Guessed I should strip the literal `sha256=` prefix and reject anything without it. No card guidance.
- **Constant-time + no-throw on length mismatch**: `timingSafeEqual` THROWS when buffer lengths differ (Node behavior from memory). To satisfy "MUST NOT throw on length mismatch" I guard with a length check first and return false. This length check is itself not constant-time, but it only reveals digest *length* (fixed at 32 bytes for sha256), not content — judged acceptable. This was entirely my own design; no recipe.
- **Bad hex in the provided signature**: `Buffer.from(x,'hex')` silently drops invalid chars rather than throwing, so a malformed hex just yields a wrong/short buffer → length or content mismatch → false. Wrapped in try/catch defensively anyway. Guessed this is the desired behavior (treat as bad signature, not crash).
- **Comparing decoded bytes vs comparing hex strings**: I decode both to bytes and compare. Alternative was to hex-encode the expected and string-compare; chose byte compare so `timingSafeEqual` gets fixed-width inputs. My call.

## Idempotency / dedupe-by-key (NOT IN BANK — first principles)
No card, no repo. Whole design is mine:

- **Race-safety via single atomic SQL statement**: used `INSERT OR IGNORE` against a `PRIMARY KEY` on `idempotency_key`. This collapses check-then-act into one atomic op — concurrent duplicates can't both insert. Guessed this is the intended "atomic, no check-then-act gap" approach. Alternative (a transaction wrapping SELECT-then-INSERT) is also valid but has a wider window under WAL; chose the constraint-based approach.
- **Distinguishing first-insert from duplicate**: relied on `info.changes` from better-sqlite3's `.run()` (0 = ignored = duplicate, 1 = inserted). API shape recalled from memory; the card only showed `.run(1)` returning nothing in its example, so the `changes` field is a guess from prior knowledge.
- **Returning the ORIGINAL id on duplicate**: on a duplicate I do a follow-up SELECT to fetch the stored id. Guessed the spec's "<same id as original>" means the persisted id, so I store the generated id and read it back.
- **ID generation**: spec says "generated id" with no format. Used `crypto.randomUUID()`. Pure guess on format.

## SQLite persistence (FULL card)
- Card was complete. Added `journal_mode = WAL` (mentioned as a feature in the card) for better concurrent-read behavior under the race scenario — minor judgment call.
- Table schema (`idempotency_key`, `raw_body`, `id`) is my own design; card only showed a toy `t(x)` table.

## Validation (FULL card)
- Card was complete. `new Ajv()` default options used as shown. Did not enable any draft-specific flags — guessed draft-07 default is fine since the card lists it first.
