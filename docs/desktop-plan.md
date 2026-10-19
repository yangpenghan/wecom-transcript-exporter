# Desktop implementation plan

Goal: ship the authorized complete Windows HTML export journey, preserving the existing native decoder.

Spec: [desktop-design.md](desktop-design.md). Run implementation inline; obtain a fresh final review as required by the execution workflow.

- [x] Build a local service layer: user-specific storage, bounded discovery, database validation, local-access consent, asynchronous jobs, fresh-snapshot recording list/export, actionable errors, allowed output files. Write synthetic behavior tests first.
- [x] Add a loopback HTTP application and windowless entry point: session protection, exact origin/host checks, bounded request bodies, safe static files, native pickers, restricted downloads/open-folder, explicit exit and idle shutdown. Verify with real HTTP tests.
- [x] Materialize approved design assets, implement the four-step HTML/CSS/JS experience with no external requests, and inspect synthetic success/empty/error states and narrow layouts in a browser.
- [x] Package a portable Windows application, update source launcher/setup and end-user documentation, and test real export plus relocated executable startup. Keep build dependencies separate from runtime dependencies.
- [x] Review, inspect tracked files/release archive for private material, run relevant tests, commit and push to the existing private repository. Publish a versioned portable ZIP with usage notes and checksum when verified. (v1.1.0 shipped; v1.2.0 public preparation is tracked separately.)

Constraints: no foreground transcript automation; original text remains verbatim; no administrator prompt or enterprise credentials; no whole-disk/user-directory scan; no personal recording in Git or release archives. Persistent authorization already covers implementation and GitHub upload. Optional platform input does not block independent Windows work.
