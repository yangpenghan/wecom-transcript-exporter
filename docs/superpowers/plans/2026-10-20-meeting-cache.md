# Meeting cache export implementation plan

**Goal:** Add general local meeting-transcript discovery and MD/JSON export to the existing Chinese portable application.

**Spec:** The user approved integrating the verified local-cache route into the existing HTML interface. No browser login, mouse automation, network requests, hard-coded meeting titles or private identifiers.

**Architecture:** A separate meeting engine reads the selected profile's account identity and its Chromium Local Storage LevelDB. Use a bounded, stable temporary snapshot and the manifest's active records, resolve latest sequence/tombstones, then validate meeting-specific JSON. Existing service/export security and file publication remain shared. Source selection occurs before connecting, so meetings do not require decrypting the face-chat database.

**Tech stack:** Python, existing HTML/CSS/JS, a minimal Apache-2.0 dfindexeddb parser subset plus pinned Windows-compatible compression wheels.

## Tasks

- [x] Test account isolation, latest records/deletions, invalid payloads, exact text and repeated utterances, multi-segment timestamps, empty caches and stable snapshots.
- [x] Implement `native_meetings.py`, share account identity resolution without requiring a contacts database, and document vendored parser provenance/licenses.
- [x] Add explicit source selection to service and UI, clear stale selections on source/account switches, explain missing caches and completeness limits.
- [x] Run Python/browser regression and real local export through the portable executable; compare against the previously verified cache export.
- [x] Independent review; privacy audit; build and publish v1.4.0 using existing authorization.

## Review focus

Reject another account's key prefix even when it appears in the same browser storage. Never recover deleted/obsolete records. Reject a cache that changes during reading. Do not silently publish malformed partial entries. Mark every meeting export as local-cache-only, with server completeness unverified.

## Decisions

Retain the existing profile-location selector as the account anchor; do not ask users to find a LevelDB directory. Read profile identity without needing `Data/user.db`. Source mode is explicit rather than decrypting face-chat data while listing meetings. No additional permissions or network services.

Validation: 62 tests ran (61 pass, 1 skip); two synthetic browser journeys; real portable meeting and face-chat exports; independent review fixes verified. Release/privacy audit follows the existing explicit publication authorization.
