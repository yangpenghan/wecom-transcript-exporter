"""Read-only SQLite access and atomic, private local output files."""

import contextlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


def configure_stdio():
    """Chinese transcripts and JSON use UTF-8 even through Windows pipes."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def connect_readonly(path, *, immutable=False):
    uri = Path(path).expanduser().resolve().as_uri() + "?mode=ro"
    if immutable:
        uri += "&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def quote_identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


def private_mkdir(path):
    missing = []
    path = Path(path)
    while not path.exists():
        missing.append(path)
        path = path.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)


@contextlib.contextmanager
def atomic_output(path, *, binary=False, newline=None, overwrite=True):
    """Publish only a complete file. Failures leave the previous output intact."""
    path = Path(path)
    private_mkdir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".wecom-", suffix=".tmp", dir=path.parent)
    try:
        if binary:
            stream = os.fdopen(fd, "wb")
        else:
            stream = os.fdopen(fd, "w", encoding="utf-8", newline=newline)
        with stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # Same-directory hard link publishes atomically without replacing a
            # destination created by another export after our preflight check.
            os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_database(path):
    """Check ordinary b-trees without loading WeCom's unavailable ICU tokenizer.

    wxSQLite3 has no page HMAC. SQLite checks detect structural corruption;
    they do not provide cryptographic authentication of message contents.
    """
    with contextlib.closing(connect_readonly(path, immutable=True)) as conn:
        tables = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
        virtual = [name for name, sql in tables if sql and sql.lstrip().upper().startswith("CREATE VIRTUAL")]
        for name, _ in tables:
            if name in virtual or any(name.startswith(v + "_") for v in virtual):
                continue
            result = [r[0] for r in conn.execute("PRAGMA quick_check(" + quote_identifier(name) + ")")]
            if result != ["ok"]:
                raise ValueError("SQLite integrity check failed: " + "; ".join(result[:3]))
