# Local Markdown Issue Tracker

This repository uses local Markdown issues until Robert explicitly approves a remote tracker.

## Wayfinding operations

- Store each effort at `docs/wayfinder/<effort>/`, with one `map.md` and one file per child ticket under `tickets/`.
- Ticket frontmatter is authoritative: `title`, `type`, `status`, `assignee`, and `blocked_by`.
- The frontier is every `open` ticket with `assignee: null` whose `blocked_by` tickets are all `closed`.
- Claim a ticket before work by setting `assignee`. Parallel agents must edit distinct ticket and asset files.
- Resolve a ticket by adding `## Resolution`, setting `status: closed`, then linking its title and one-line gist under the map's `Decisions so far`.
- Refer to tickets by linked title in human-facing text. Filenames are storage identifiers, not names.
- Keep unresolved ticket details out of the map. Use `Not yet specified` only for in-scope questions that cannot yet be stated precisely.

Research assets live under `docs/research/` and are linked from the resolving ticket.
