"""Standalone background export of the signed-in user's cached WeCom face chats."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

from native_support.wxwork_crypto import decrypt_database, verify_key
from native_support.local_io import atomic_output
from native_transcript import extract_room, format_time, render_markdown, room_catalog

ROOT = Path(__file__).resolve().parent
NO_WINDOW = 0x08000000


class DataBlob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def unprotect_key(path):
    protected = path.read_bytes()
    storage = (ctypes.c_ubyte * len(protected)).from_buffer_copy(protected)
    source, result = DataBlob(len(protected), storage), DataBlob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.memset(result.data, 0, result.size)
        kernel32.LocalFree(result.data)


def powershell(args, timeout):
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    return subprocess.run([str(executable), '-NoProfile', *args], capture_output=True, timeout=timeout,
                          creationflags=NO_WINDOW, encoding='utf-8', errors='replace')


def database_key(database, state):
    with database.open('rb') as stream:
        page = stream.read(4096)
    key_file = state / 'voice-room-key.dpapi'
    if key_file.exists():
        try:
            key = unprotect_key(key_file)
            if verify_key(key, page):
                return key, 'reused protected key'
        except (OSError, ValueError):
            pass
    result = powershell(['-Command', """
$ErrorActionPreference='Stop'
$currentSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$currentSession=(Get-Process -Id $PID).SessionId
@(Get-CimInstance Win32_Process -Filter "Name='WXWork.exe'" | Where-Object {
    $_.SessionId -eq $currentSession -and
    (Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid).Sid -eq $currentSid
} | Select-Object -ExpandProperty ProcessId) | ConvertTo-Json -Compress
"""], 15)
    if result.returncode:
        raise RuntimeError('Unable to identify the current Windows user\'s WeCom process')
    pids = json.loads(result.stdout or '[]')
    if isinstance(pids, int):
        pids = [pids]
    if len(pids) != 1:
        raise RuntimeError('Open and sign into one WeCom desktop instance, then retry. It can remain in the background.')
    print('Checking the local database key (read-only; up to 40 seconds)...', flush=True)
    # Scope script-policy handling to this reviewed bundled helper process.
    # Machine and user policies are never changed; managed policy still applies.
    result = powershell(['-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'native_support/scan_voice_room_key.ps1'),
                         '-ProcessId', str(pids[0]), '-Database', str(database), '-Seconds', '40',
                         '-OutputDirectory', str(state)], 55)
    report_path = state / 'scoped-key-probe.json'
    if result.returncode or not report_path.exists():
        raise RuntimeError('Read-only database-key check failed. No desktop automation was started.')
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    if not report.get('found'):
        raise RuntimeError('No verified key found within the bounded check; this client version needs investigation.')
    key = unprotect_key(key_file)
    if not verify_key(key, page):
        raise RuntimeError('Database key failed full-page validation')
    return key, 'verified local process key'


def choose_database(explicit):
    if explicit:
        database = Path(explicit).expanduser().resolve(strict=True)
        if database.name != 'voice_room5.db':
            raise ValueError('This version supports voice_room5.db only')
        return database
    candidates = sorted((Path.home() / 'Documents/WXWork/Profiles').glob('*/voice_room5.db'))
    if len(candidates) != 1:
        raise ValueError('Expected one local profile. Use --database with the intended voice_room5.db path.')
    return candidates[0].resolve()


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', help='Explicit voice_room5.db for a relocated or multiple-account installation')
    parser.add_argument('--title', help='Exact title from the local session list')
    parser.add_argument('--list', action='store_true', help='Show cached face-to-face sessions without exporting')
    parser.add_argument('--output', type=Path, help='Markdown destination; existing files are not overwritten')
    parser.add_argument('--speaker-map', type=Path, help='Optional JSON mapping of sender IDs to display names')
    args = parser.parse_args(argv)
    began = time.perf_counter()
    database = choose_database(args.database)
    profile_tag = hashlib.sha256(str(database).encode()).hexdigest()[:16]
    state = ROOT / '.native-state' / profile_tag
    state.mkdir(parents=True, exist_ok=True)
    key, key_method = database_key(database, state)
    aliases = json.loads(args.speaker_map.read_text(encoding='utf-8')) if args.speaker_map else {}
    with tempfile.TemporaryDirectory(prefix='snapshot-', dir=state) as temp:
        plain = Path(temp) / 'voice-room.db'
        decrypt_database(database, plain, key)
        conn = sqlite3.connect(plain.as_uri() + '?mode=ro&immutable=1', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rooms = room_catalog(conn)
            if not rooms:
                raise RuntimeError('No face-to-face sessions are cached locally')
            if args.list or not args.title:
                for index, room in enumerate(rooms, 1):
                    print(f'{index:2}. {room["title"]}  [{format_time(room["started"])}]')
            if args.list:
                return 0
            if args.title:
                chosen = [r for r in rooms if r['title'] == args.title]
                if len(chosen) != 1:
                    raise ValueError('Title not found or ambiguous. Run without --title to select a numbered session.')
                room = chosen[0]
            else:
                value = input('\nSession number to export (Enter to cancel): ').strip()
                if not value:
                    return 0
                index = int(value)
                if not 1 <= index <= len(rooms):
                    raise ValueError('Session number is out of range')
                room = rooms[index - 1]
            result = extract_room(conn, room['room_id'], aliases)
        finally:
            conn.close()
    # All plaintext database snapshots are removed before publishing the selected transcript.
    title = room['title']
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:100] or 'transcript'
    destination = args.output or ROOT / 'exports/native' / f'{safe_title}-{datetime.now().strftime("%Y%m%d-%H%M%S")}.md'
    destination = destination.resolve()
    if destination.suffix.lower() != '.md':
        raise ValueError('Output must end in .md')
    json_path = destination.with_suffix('.json')
    if destination.exists() or json_path.exists():
        raise FileExistsError('Output already exists; choose a new filename')
    result.update(title=title, key_method=key_method, elapsed_seconds=round(time.perf_counter() - began, 3))
    with atomic_output(json_path, overwrite=False) as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    with atomic_output(destination, newline='\n', overwrite=False) as stream:
        stream.write(render_markdown(title, result))
    print(f'Exported {len(result["records"])} passages in {result["elapsed_seconds"]:.2f}s: {destination}')
    if result['missing_id_ranges'] or not result['last_segment_ended']:
        print('Cache coverage warning: inspect the JSON report before treating this as complete.')
    if result['unresolved_speakers']:
        print('Some member display names are absent from this cache; stable member labels are used.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        print(f'Export stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
