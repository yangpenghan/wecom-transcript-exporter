# Third-party notices

Original project code is licensed under Apache-2.0; see `LICENSE` and `NOTICE`. That license does not replace the separate licenses below or grant trademark endorsement.

The database crypto, WAL, local I/O helpers, Windows key scanner, and WAL test fixtures are adapted from [freanocank/wecom-agent](https://github.com/freanocank/wecom-agent), under the MIT license. Upstream notices include copyright (c) 2026 tzwkb.

The complete license is retained at [`native_support/LICENSE.wecom-agent`](native_support/LICENSE.wecom-agent). Source URLs, upstream hashes where recorded, local hashes, and adaptation notes are retained in [`native_support/PROVENANCE.json`](native_support/PROVENANCE.json).

Runtime dependencies are installed separately from `requirements-lock.txt`: `cryptography`, `cffi`, and `pycparser`. Their distributions include their respective license files. Python and dependency binaries are not included in this Git repository.

The HTML interface includes Will Yang's personal design assets and locally bundled IBM Plex Sans / Noto Sans SC fonts. Font and seal notices are retained under `web/will-assets/personal/`. `web/will-usage.json` records asset hashes and the design-token version.

Portable releases bundle Python, cryptography and their required binary components using PyInstaller. Runtime and packaging license notices are copied into the release's `licenses/` directory and the bundled dependency metadata.

## Local meeting cache reader

`dfindexeddb/` contains an unmodified minimal LevelDB parser subset from Google's [dfindexeddb](https://github.com/google/dfindexeddb), PyPI release `20260210`, under Apache-2.0. The upstream copyright headers, `dfindexeddb/LICENSE`, and file hashes in `dfindexeddb/PROVENANCE.json` are retained. IndexedDB and CLI modules are not included. Project-owned integrity checks wrap this parser.

Additional pinned runtime dependencies: python-snappy 0.7.3 (BSD), cramjam 2.14.0 (MIT, with bundled codec notices), zstd 1.5.7.2 (BSD), and google-crc32c 1.9.0 (Apache-2.0). Their distribution license files are copied into portable releases. Newer Windows-compatible compression packages are used instead of the upstream package's older exact dependency pins; the selected reader subset is tested against these versions. Zstandard SST blocks are currently rejected by the bounded reader; zstd remains required by the vendored module import.
