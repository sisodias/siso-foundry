# Provenance

## Initial extraction

- Date: 2026-07-30
- Source inventory: `gls:source-inventory:d3e37616-1005-4d67-b5c5-82684dceed70`
- Destination Work: `gls:work:ec664d93-df93-48c5-be40-5d0165886c01`

The initial source was read from the SISO Agent Base warehouse's `foundry`, `research/repo-catalog`, and `extensions/research-topics` areas. The warehouse checkout contained pre-existing tracked and untracked work, so this extraction preserves selected current file content without claiming that it corresponds to the warehouse's last public commit.

The public repository includes coherent software and contracts from:

- `foundry/core`;
- `foundry/domains/github`, excluding generated browser and bank exports;
- `foundry/domains/people`, `youtube`, and the podcast domain contract;
- `foundry/research/wild3/bank.py` and the reusable verification-rig source;
- `extensions/research-topics`.

Excluded from Git publication:

- SQLite databases and WAL files;
- raw corpus rounds and harvest shards;
- staging outputs, generated reports, logs, run sandboxes, dependency folders, and caches;
- launchd files, host-specific dispatch scripts, personal absolute paths, and internal operator state;
- third-party source payloads whose ownership remains with their upstream projects.

Host paths were replaced with `FOUNDRY_DATA` and narrower environment overrides. Dataset observations are recorded without publishing personal storage locations.
