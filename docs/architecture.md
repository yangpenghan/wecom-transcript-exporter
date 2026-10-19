# Implementation and limits

The sections below describe the shared native reader and CLI. The normal browser workflow is documented in [the portable guide](portable-guide.md) and [desktop design](desktop-design.md). Its `desktop_service.py` adapter stores preferences and protected keys in the current user's LocalAppData and uses process-owned snapshot directories so abandoned snapshots can be cleaned safely on restart.

## Data path

1. Find `Documents/WXWork/Profiles/*/voice_room5.db`, or use the explicit `--database` path. Multiple profiles require an explicit choice.
2. Reuse a verified, Windows DPAPI CurrentUser-protected database key. On first use, select the current Windows user's WeCom process in the same session and run a bounded read-only key check. The helper does not enable debug privileges, inject code, suspend the process, or write process memory.
3. Read the database and WAL twice in opposite order. Require identical contents and metadata, validate WAL generation/checksums, and apply only committed frames. Retry changing files up to three times. This is a repeated-content check, not a transactionally locked SQLite backup.
4. Decrypt an isolated temporary snapshot using the observed wxSQLite3 AES-128 format, then check ordinary SQLite tables. WeCom's custom FTS tokenizer is unavailable, so virtual FTS tables are not checked.
5. Select one room, decode original utterances from its native message payloads, and preserve recording restarts as separate segments. Search-index tokens and summary text are not substituted for the original utterances.
6. Remove the temporary database snapshot. Publish Markdown and JSON as separate complete files with atomic, no-overwrite hard links.

## Responsibilities

| File | Responsibility |
| --- | --- |
| `native_export.py` | CLI, profile selection, protected key handling, snapshot lifetime, export publication |
| `native_transcript.py` | Native payload decoding, room catalog, coverage indicators, Markdown |
| `native_support/scan_voice_room_key.ps1` | Bounded read-only key check scoped to current user/session |
| `native_support/wxwork_crypto.py` | Database page decryption and validation |
| `native_support/wal_snapshot.py` | Repeated-content snapshot checks and committed WAL frames |
| `native_support/local_io.py` | Read-only SQLite access and atomic output |
| `tests/` | Synthetic payload, WAL, corruption and output-collision tests |

## Observed schema

The adapter uses `voice_room_message` and the observed `room_id`, `rid`, `sender`, `sender_name`, `send_time`, `content_type`, and `blob` columns. Text records use `content_type=2`; the original UTF-8 text is at protobuf field path `8 → 1 → 2 → 1`. Native state field 13 is included only when zero; excluded nonzero-state records are counted in the report. This policy is conservative: nonzero state is not asserted to mean deletion.

Create, restart, and end markers delimit recording segments. Title-change control messages provide room titles. Numeric message gaps and the final end marker provide coverage indicators. They cannot prove that the server has no additional records.

## Practical limits

- Tested with Windows WeCom 5.0.12.6018 and 64-bit Python 3.13. A client update can change the schema, encryption, key location, or payload format.
- The source is the signed-in account's local cache. Open a missing recording normally in WeCom so it can synchronize, then retry the export.
- A missing final end marker or message-ID gaps produce a warning. Unsupported payloads stop export rather than silently dropping text.
- Blank member display names receive stable `成员N` labels; JSON retains sender identifiers for optional local name mapping.
- The bundled PowerShell helper is launched with a process-scoped execution policy so ordinary local script restrictions do not break setup. No persistent policy is modified. Organization-enforced policy remains authoritative; a blocked helper causes export to stop.
- The first key check has a 40-second scan budget plus process discovery and compilation overhead. If it fails, no foreground automation starts.
- DPAPI state is tied to the current Windows account. Do not copy it to another computer as part of installation.
- Output publication needs hard-link support, such as a local NTFS volume. Unsupported destinations fail; use a local folder first. The Markdown/JSON pair is not a single transaction: if Markdown publication fails, a complete JSON sidecar may remain. Choose a new output name when retrying.
- Decrypted temporary snapshots are removed during normal completion and handled errors. Forced process termination can leave a `snapshot-*` folder inside `.native-state`; it can be removed when no exporter is running.

## Why the other routes were retired

The tested official CLI meeting endpoints exposed online meetings but did not resolve the face-chat link. The summary's `wxwork://jump?target=voice_chat_room&scheme=…` link identified the native face-chat subsystem. That led to `voice_room5.db` and the working local adapter. This is an observation about the tested client and CLI, not a claim that future official APIs cannot support export.

The earlier foreground OCR/copy workflow required repeated scrolling and clipboard operations. Its scripts, models, screenshots, and obsolete tests have been removed from this release.

## Validation

Run `python -m unittest discover -s tests -v` after installing the pinned dependencies. Tests create synthetic databases and payloads; they do not open WeCom, inspect a live process, or use private recordings.

The initial real-recording check exported 347 utterances. Its first 346 matched the earlier copy-based result exactly; one additional utterance belonged to a resumed segment. The first export took 3.44 seconds and a repeat took 0.32 seconds on the development machine. These are measured examples, not performance guarantees. Real test recordings and reports are deliberately excluded from Git.
