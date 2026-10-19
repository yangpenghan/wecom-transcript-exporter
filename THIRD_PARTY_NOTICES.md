# Third-party notices

Original project code is licensed under Apache-2.0; see `LICENSE` and `NOTICE`. That license does not replace the separate licenses below or grant trademark endorsement.

The database crypto, WAL, local I/O helpers, Windows key scanner, and WAL test fixtures are adapted from [freanocank/wecom-agent](https://github.com/freanocank/wecom-agent), under the MIT license. Upstream notices include copyright (c) 2026 tzwkb.

The complete license is retained at [`native_support/LICENSE.wecom-agent`](native_support/LICENSE.wecom-agent). Source URLs, upstream hashes where recorded, local hashes, and adaptation notes are retained in [`native_support/PROVENANCE.json`](native_support/PROVENANCE.json).

Runtime dependencies are installed separately from `requirements-lock.txt`: `cryptography`, `cffi`, and `pycparser`. Their distributions include their respective license files. Python and dependency binaries are not included in this Git repository.

The HTML interface includes Will Yang's personal design assets and locally bundled IBM Plex Sans / Noto Sans SC fonts. Font and seal notices are retained under `web/will-assets/personal/`. `web/will-usage.json` records asset hashes and the design-token version.

Portable releases bundle Python, cryptography and their required binary components using PyInstaller. Runtime and packaging license notices are copied into the release's `licenses/` directory and the bundled dependency metadata.
