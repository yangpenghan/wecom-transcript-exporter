# Verification history

## v1.4.0 — Local meeting transcripts

Tested on 2026-10-20. All 62 Python tests completed: 61 passed and one POSIX-only test was skipped. New tests cover exact account/key isolation, latest values and tombstones, meeting-only profiles, repeated utterances and multi-segment timestamps, malformed/empty payloads, stable snapshot cleanup, previous-log inclusion, CRC corruption, incomplete fragments and decompression size limits. Independent review confirmed the integrity and discovery fixes.

Both synthetic browser journeys passed: existing face-chat behavior and the new source selector, account discovery, safe plaintext preview, unavailable/empty/error states, completeness warning and mobile layout. The 390px meeting view was visually inspected.

The built v1.4.0 executable exported the approved real meeting through its browser UI: 253 passages, all text/speakers/offsets/content IDs matched the previously verified local cache export, and export took 0.301 seconds. Switching to face-chat mode exported 347 passages with four resolved names. There were zero external browser requests, and Exit stopped the app. Meeting server completeness remains unverified. No private title, meeting identifiers, names or content are included in this verification document.


## v1.3.0 — Optional local speaker names

The selected recording's four unresolved member IDs each matched exactly one name in the current account's local contact cache. The production service exported all 347 passages with those names; every non-speaker record field and each existing native name stayed unchanged. Initial contact access plus export took 10.271 seconds in this test; later checks reuse the protected contact key. Names, IDs, contact data and the verified private export remain outside Git.

45 synthetic Python tests ran: 44 passed and one POSIX-only test was skipped. Coverage includes exact account selection, malformed/duplicate identity, large IDs, conflicting names, ID-limited queries, no default contact access, original text/native-name preservation, optional-failure fallback and revocation of both keys. Review found and fixed cleanup of interrupted decryption staging files; a regression test verifies cleanup for dead processes while preserving active snapshots. The browser journey passed with the option initially unchecked, explicitly selected before export and sent as a boolean to the service; desktop/narrow layouts remained within the viewport.

The packaged v1.3.0 Windows executable also exported the same recording through the real browser interface: 347 passages, four resolved names, exact record equality with the independently verified service export, and zero external browser requests. The application exited successfully from its interface.

## v1.2.0 — Simplified Chinese interface

This independent distribution repository was initialized from the audited source allowlist. Runtime code and UI match the tested development build; the portable guide points to this repository's Releases page. No development Git objects or user state were copied.

Tested on 2026-10-19. The UI uses `zh-CN`, horizontal writing and bundled Noto for Chinese. Buttons, labels, help, errors, progress messages, native picker captions, README and portable guide are localized; original recording content remains untouched.

The 33 Python tests completed with 32 passes and one POSIX-only skip. The synthetic Chromium journey passed, including error recovery, exact 64-bit recording identifiers and safe plaintext preview. Layout checks covered 320, 390, 430, 768, 1024 and 1440px widths and 200% CSS zoom. Desktop and 390px mobile screenshots were visually inspected. Rendered-font inspection confirmed bundled Noto for Chinese preview and visible headings. No horizontal overflow remained after fixing long-path wrapping and grid minimum widths. These checks do not certify every browser's Chinese line-breaking behavior.

The built v1.2.0 executable also passed the synthetic browser journey and real local HTTP checks for runtime readiness, authentication, Chinese error responses and clean shutdown. Its ZIP SHA-256 matched the checksum. No live recording was needed for this localization regression; the earlier real-export evidence below remains separately dated.

Privacy findings and remediation are documented in [privacy-audit.md](privacy-audit.md); publication status is in [public-release-checklist.md](public-release-checklist.md).

## v1.1.0

Tested on 2026-10-19, Windows 11 x64, Python 3.13.14, WeCom 5.0.12.6018.

- **Python:** 33 synthetic tests ran; 32 passed and one POSIX-permissions test was skipped on Windows. Coverage includes native text preservation, WAL integrity, no-overwrite output, discovery, explicit consent, exact large room IDs, failed account switching, stale snapshot cleanup, HTTP session/origin/host enforcement, traversal and two simultaneous app instances.
- **Browser:** synthetic fixtures exercised missing and multiple profiles, consent gating, failed connection and retry, title filtering, exact room IDs, export, safe original-text rendering, responsive layout, help, empty recording lists and failed-refresh recovery. Desktop 1440px and mobile 390px layouts were inspected. No horizontal overflow was found.
- **Fonts:** Chromium's rendered-font inspection verified locally bundled Noto for Chinese preview text and Plex for visible English headings, including the recording and help states. The generic initial-state design validator reports no fonts for hidden headings; those headings were therefore checked in their actual visible interactive states instead of treating the static report as a pass.
- **Real portable workflow:** extracted the release into a different directory containing spaces, launched its windowless executable with system-only PATH and no PYTHONHOME/PYTHONPATH, connected with a fresh protected-key state, and completed export through the actual browser interface. All 347 original passages exactly matched the previously verified output. The export stage took 0.329 seconds; initial access is a separate operation. No external browser requests occurred. Exit shut down the application.
- **Discovery:** one real profile found in two folders in approximately 0.002 seconds. Discovery prunes media trees after finding a profile and bounds manual searches by depth, entries and elapsed time.
- **Review:** all three review findings were fixed and re-reviewed: cross-port cookie collision, abandoned plaintext snapshots, and stale UI state after refresh failure.

Real recordings, protected keys, local paths, test screenshots with live data, and local session connection files are excluded from Git and release archives. The README screenshot uses synthetic profiles.

Deployment limits: no second physical Windows computer was available. The executable is unsigned. Organization policy, a different WeCom build, unsupported CPU architecture, or storage permissions can still prevent use; the interface and portable guide explain recovery paths. Successful local export is not a certification of server-side completeness.
