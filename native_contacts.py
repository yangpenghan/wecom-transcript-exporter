"""Resolve only requested speaker IDs from the selected account's local cache."""
import base64
from collections import defaultdict
import contextlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

from native_transcript import decode_fields, _single


def contact_database(database):
    database = Path(database).resolve(strict=True)
    profile = database.parent
    if profile.parent.name.casefold() != 'profiles':
        raise ValueError('Selected recording cache is outside a supported profile layout')
    identity = (profile / 'io_data.json').resolve(strict=True)
    if not identity.is_relative_to(profile):
        raise ValueError('Identity file is outside the selected profile')
    with identity.open('rb') as stream:
        raw = stream.read(1048577)
    if len(raw) > 1048576:
        raise ValueError('Profile identity file exceeds the supported size')
    data = json.loads(raw)
    encoded = data.get('user_info') if isinstance(data, dict) else None
    if not isinstance(encoded, str) or len(encoded) > 4096:
        raise ValueError('Missing profile identity')
    uid = _single(decode_fields(base64.b64decode(encoded, validate=True)), 1)
    if not isinstance(uid, int) or not 0 < uid <= 2**63 - 1:
        raise ValueError('Invalid profile identity')
    account = profile.parent.parent / str(uid)
    contact = (account / 'Data/user.db').resolve(strict=True)
    if not contact.is_relative_to(account) or not contact.is_file():
        raise ValueError('Contacts are outside the selected account')
    if contact.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('Contact cache exceeds the supported size')
    return contact


def query_names(conn, speaker_ids):
    ids = sorted({int(value) for value in speaker_ids
                  if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,18}', value)
                  and int(value) <= 2**63 - 1})
    candidates = defaultdict(set)
    for start in range(0, len(ids), 400):
        chunk = ids[start:start + 400]
        placeholders = ','.join('?' for _ in chunk)
        for uid, name in conn.execute(f'SELECT id,name FROM user_table WHERE id IN ({placeholders})', chunk):
            if isinstance(name, str) and name.strip() and name != '-':
                candidates[str(uid)].add(name)
    return {uid: next(iter(names)) for uid, names in candidates.items() if len(names) == 1}


def resolve_names(database, state, speaker_ids, progress):
    """Optional enrichment: failure never prevents exporting the transcript."""
    ids = list(dict.fromkeys(speaker_ids))
    report = {'status': 'not_needed', 'requested': len(ids), 'resolved': 0}
    if not ids:
        return {}, report
    try:
        contact = contact_database(database)
        # A separate sibling profile state keeps both keys isolated and lets the
        # existing revoke/dead-process cleanup cover contact state as well.
        state = Path(state)
        contact_state = state.with_name(state.name + '-contacts')
        contact_state.mkdir(parents=True, exist_ok=True)
        from native_export import database_key
        from native_support.wxwork_crypto import decrypt_database
        progress('正在核验本地通讯录权限，首次检查可能需要约一分钟……')
        key, _ = database_key(contact, contact_state)
        progress('正在按成员 ID 精确匹配姓名……')
        with tempfile.TemporaryDirectory(prefix=f'snapshot-{os.getpid()}-', dir=contact_state) as directory:
            plain = Path(directory) / 'voice-room.db'
            decrypt_database(contact, plain, key)
            with contextlib.closing(sqlite3.connect(plain.as_uri() + '?mode=ro&immutable=1', uri=True)) as conn:
                names = query_names(conn, ids)
        report.update(status='complete' if len(names) == len(ids) else 'partial', resolved=len(names))
        return names, report
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError):
        report['status'] = 'unavailable'
        return {}, report
