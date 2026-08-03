# Mac mini + vault + laptop — storage layout and agent on-ramp

Verified state as of 2026-08-03. Everything below was measured over SSH, not assumed.

## Machines and roles

| Machine | Role | Reachable via |
| --- | --- | --- |
| MacBook Pro | Source of truth for CODE. Where work is authored, committed, pushed. | — |
| Mac mini (M4, macOS 15.5, `Shaans-Mac-mini.local`) | Always-on control node. Runs collectors, agents, services. | `ssh mini-fast` (Tailscale, tailnet `fuzeheritage@`) + Cloudflare Tunnel (permanent) |
| SISO-STORAGE-VAULT | 5 TB external. Mass + cold storage. | `/Volumes/SISO-STORAGE-VAULT 1` on the mini |
| GitHub | Durable distribution + offsite backup. | public repos + release assets |

## The physical constraint that drives every decision

The vault is on **USB 2.0: 480 Mb/s, ~40 MB/s real**, with zero power headroom
(needs 500 mA, gets 500 mA) and **SMART unreadable** through the USB bridge.
The internal SSD is several thousand MB/s. That is a 50-100x gap.

Consequence: the split is by ACCESS PATTERN, not by size.

- Live SQLite (WAL does constant small synchronous writes) must stay internal.
  Putting Foundry's `domains/` on USB 2.0 would be slower than today and risks
  WAL corruption on a bus that can brown out.
- Sequential bulk reads/writes are fine on the vault.

Fixing this is a ~£20 problem: a powered USB-C hub or enclosure takes it to
USB 3 (~400+ MB/s) and makes SMART readable. Worth doing before the vault holds
the whole library.

## Three tiers

**Internal SSD (228 GB, 65 GB free) — HOT working set**
Live databases, active git checkouts, anything a running agent touches.
Homebrew (12 GB at `/opt/homebrew`) and `~/Library` (10 GB) cannot move.

**Vault (4.5 TB, 3.9 TB free) — MASS + COLD**
Book payloads, scraped archives, raw transcripts, backups, finished work.
Write-once-read-occasionally.

**GitHub — DURABLE DISTRIBUTION**
Release assets do not count against repo size (measured: yt-dlp reports 60 MB
repo while carrying 1.67 GB across three releases). 2 GiB per asset, 1000 assets
per release, no documented cap on total release size. HTTP Range returns 206 on
both raw and release URLs, so a single book can be pulled from a large archive
without downloading it whole.
Caveat: AUP prohibits "excessive automated bulk activity" — GitHub is a
warehouse, not a working disk. Cache locally, don't hammer it.

This tier makes the vault's unreadable SMART status survivable: if the drive
dies, re-pull rather than lose.

## Current vault layout (created 2026-08-03)

```
/Volumes/SISO-STORAGE-VAULT 1/
├── library/
│   ├── gutenberg/            # 11.2 GB plaintext corpus (not yet pulled)
│   ├── internet-archive/     # second adapter, later
│   └── _catalog/             # books.sqlite (182 MB metadata module)
├── cold-storage/
│   └── oracle-gate/          # 8.5 GB, 215,462 files — VERIFIED complete
├── from-internal-ssd-20260803/  # 12 GB decoy content — VERIFIED 112/112 files
├── foundry-data/             # pre-existing
├── archives/  backups/
└── SISO-VAULT/               # 23 dirs, pre-existing
```

## Known traps

**Mount-point collision.** The vault mounts as `SISO-STORAGE-VAULT 1` (trailing
space-one) because a 12 GB *folder on the internal SSD* holds the clean name
`/Volumes/SISO-STORAGE-VAULT`. Anything hardcoding the clean path today writes
to the INTERNAL DISK and appears to work. This is how the 12 GB got there.
Fix: rename the decoy (do not delete), then remount.

**TCC blocks removable-volume writes from SSH sessions.** Writing to the vault
root as `shaansisodia` over SSH fails with Permission denied despite correct
ownership. `sudo` works (passwordless is enabled). A launchd job running as the
user will hit the same wall — run it as root or pre-create directories.

**`du` on large trees times out over USB 2.0.** A 215k-file tree took >120 s and
returned empty, which reads as "copy failed" when it succeeded. Verify with
`find | wc -l` and `df` deltas, not `du`, on this drive.

**The mini is running almost nothing.** Only `com.cloudflare.cloudflared`.
No Foundry collectors, no `com.siso.*` launchd jobs — despite the architecture
describing the mini as the always-on engine. Whatever was scheduled is not
running. Investigate before assuming any pipeline is live.

## Access: how an agent reaches all of this

1. **From the laptop, to the mini:** `ssh mini-fast '<cmd>'`.
   Use `mini-fast`, never `mac-mini` — the latter sets `RemoteCommand`, so
   remote execution fails with "Cannot execute command-line and remote command."
2. **Tunnel (tailnet-independent):** `cloudflared` runs as a system launch
   daemon (`com.cloudflare.cloudflared`), four QUIC connections to London edge.
   Remaining step: add Private Network route `192.168.0.100/32` in Zero Trust,
   install WARP on the laptop. Then SSH works regardless of tailnet.
3. **Vault paths are only valid ON the mini.** A laptop-side check of
   `/Volumes/SISO-STORAGE-VAULT 1` will always fail — that path does not exist
   locally. Route vault work through SSH.

## Code vs data (the rule that keeps this coherent)

Code travels by git: author on the laptop, commit, push, pull on the mini.
Data never travels by git: it lives in the data plane (vault) or as GitHub
release assets, with rights and provenance recorded.

## Books: where the pieces are

- `books.sqlite` (182 MB) — 79,071 Gutenberg records, every upstream column
  preserved verbatim, proven lossless (all 9 columns present, 5/5 row roundtrip).
  184,624 subject edges, 206,269 shelf edges, 82,405 LoCC classification edges.
- Payload: `https://www.gutenberg.org/cache/epub/feeds/txt-files.tar.zip`
  (11,244,765,936 bytes, refreshed weekly upstream). NOT yet pulled.
- Catalog source: `https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv`
  (21 MB, 5-second download, sanctioned by Gutenberg over crawling).
- Source Inventory record drafted and schema-validated, not yet committed.

Target: payload → vault `library/gutenberg/` AND GitHub release assets (both,
so the vault is a cache and GitHub is the durable copy). Catalog → `_catalog/`.
