# Browser interface and portable Windows journey

## Intent and scope

Replace the command window as the normal user experience. A person on another Windows computer can open a portable app, locate their own WeCom data, understand local access, select a recording, and save readable files without Python installation or agent applications. Keep the existing command-line exporter for automation.

The user requested an HTML frontend, automatic discovery and manual location selection, guidance about authorization, and complete handling of another computer's first run, and confirmed a portable Windows package. Implementation choices: a local browser UI backed by the existing Python decoder; a portable Windows executable packaged in a ZIP; English interface with original multilingual recording titles. Other operating systems are outside this version's scope.

## Journey

1. Extract the entire portable folder and open `WeCom Transcript Exporter.exe`. A local browser tab opens; no command window is needed. The source checkout additionally has a double-click launcher using its configured local environment.
2. See readiness checks and a plain explanation: data stays on this computer, no enterprise API credential is requested, and each person uses their own signed-in WeCom account. Initial local access needs an explicit action/consent in the interface. Do not request Windows administrator rights or change managed security settings.
3. Auto-find databases in the current user's normal and redirected Documents locations, saved location, and known WeCom folders. Show candidates with path and modified time; never silently choose among multiple profiles. Provide a native file picker, a bounded folder search and a pasted path field. Do not scan all users or whole disks. Explain missing/moved/unsupported/unreadable databases.
4. Confirm the selected account cache and allow local read access. Connect is an asynchronous operation with real stage labels. WeCom can remain in the background. A missing process, multiple processes, failed key check, unsupported version, and unsynchronized/empty cache each produce an actionable message. Do not claim to detect sign-in positively from process existence.
5. List cached recordings, searchable by title. Select a room by stable internal ID, avoiding duplicate-title ambiguity. Choose a destination folder; default to a user-writable Documents export folder. Export original Markdown plus JSON without overwriting existing files. Refresh the snapshot for each export.
6. Show passage count, elapsed time, completeness warnings and missing-speaker-name notes. Offer a plain-text preview and buttons to download the two generated files or open their local folder. Render all private text with textContent, never as HTML.
7. Explain how to change location, retry, revoke remembered local access, and exit. Do not leave an indefinite hidden process after its browser UI is abandoned: provide explicit Exit, plus an idle shutdown after browser heartbeats stop and active work completes.

## Local state, package, and access

- Store preferences and DPAPI-protected keys under the current user's LocalAppData, outside the app installation folder. No keys, recordings, chosen paths or consent state are bundled in a release.
- Bind only to IPv4 loopback on an OS-selected port. Require a random per-process browser session and exact Host/Origin checks. No cross-origin API access. State-changing APIs are POST only; export/download access is restricted to files produced by this process. No arbitrary filesystem-reading endpoint.
- Serve bundled assets and fonts offline. No analytics, remote fonts or CDNs. The packaged app makes no outbound requests during export.
- The executable is unsigned; explain the download/extraction and organization-policy limitations in the distribution guide. Never instruct users to disable protections.
- Local Windows permission restrictions still apply. Usually normal user access suffices when WeCom runs as the same user/session; enterprise policy or unequal elevation can block access. The app reports this and does not escalate automatically.
- Native file/folder dialogs appear only after a user clicks the corresponding button.

## Interface

Use Will's personal V4.1 web tokens: paper #F4F6F8, ink #17232E, plum #433C53, active blue #285ACA, ice #A8CCD6. Locally packaged IBM Plex Sans and Noto Sans SC. A compact identity header, a meaningful four-step progress rail, and one working area keep attention on the current task. Desktop uses a recording list beside an export/preview pane; narrow screens stack the panes. Settings and help stay accessible, errors include recovery actions, busy controls are disabled, focus and live status are accessible. No marketing hero or ornamental dashboard cards.

## Validation

Synthetic service tests cover discovery, ambiguous profiles, consent gating, async failure/retry, destination validation, safe filenames, and exclusion of stale room selections. HTTP tests cover unauthorized requests, invalid Origin/Host, traversal, session establishment and download allowlisting. Browser checks cover fresh/no-data, multiple locations, connect failure, empty recordings, filtering, exporting and responsive layouts using synthetic fixtures. A real local export must exactly match the saved 347-passage result. Build and launch the packaged executable from a different directory with no source environment dependency. Verify archive contents exclude user data, keys and absolute development paths. Another physical Windows computer is not available, so report that limit.
