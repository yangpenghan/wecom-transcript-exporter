"""Read current-account meeting transcripts from a stable local LevelDB snapshot."""
import base64
import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from native_contacts import account_directory

MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
ZONE = timezone(timedelta(hours=8))
WARNING = '会议原文来自本机缓存，尚未核对服务器端完整性；缓存可能过期或不完整。'


def select_current(records, uid):
    pattern = re.compile(
        rb'_https://app\.work\.weixin\.qq\.com\x00\x01ww0_' + uid.encode('ascii') +
        rb'_/xweb/smartMinutes/getMeetingNotes/([0-9]+)')
    latest = {}
    for record in records:
        match = pattern.fullmatch(record.key)
        if not match:
            continue
        code = match[1].decode('ascii')
        if code not in latest or record.sequence_number > latest[code].sequence_number:
            latest[code] = record
    return {code: row for code, row in latest.items() if int(row.record_type) == 1}


def _read(folder, name):
    if not re.fullmatch(r'CURRENT|MANIFEST-\d+|\d+\.(ldb|log)', name):
        raise ValueError('Unsupported cache filename')
    path = folder / name
    if path.is_symlink() or path.resolve(strict=True).parent != folder:
        raise ValueError('Cache file is redirected')
    if path.stat().st_size > MAX_FILE:
        raise ValueError('Cache file exceeds supported size')
    with path.open('rb') as stream:
        data = stream.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError('Cache file exceeds supported size')
    return data


@contextlib.contextmanager
def stable_snapshot(folder, state):
    """Copy only manifest-active files, then compare every byte before use."""
    from dfindexeddb.leveldb.descriptor import FileReader
    folder = Path(folder).resolve(strict=True)
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f'snapshot-{os.getpid()}-', dir=state) as directory:
        target = Path(directory)
        current = _read(folder, 'CURRENT')
        manifest = current.decode('ascii').strip()
        manifest_data = _read(folder, manifest)
        from native_leveldb import validate_log
        validate_log(manifest_data)
        (target / 'CURRENT').write_bytes(current)
        (target / manifest).write_bytes(manifest_data)
        version = FileReader(str(target / manifest)).GetLatestVersion()
        if version is None:
            raise ValueError('Missing LevelDB manifest version')
        names = {name for level in version.active_files.values() for name in level}
        previous_log = 0
        for edit in FileReader(str(target / manifest)).GetVersionEdits():
            if edit.prev_log_number is not None:
                previous_log = edit.prev_log_number
        if previous_log:
            names.add(f'{previous_log:06d}.log')
        if version.current_log:
            names.add(version.current_log)
        # A newer log can contain writes after the last manifest checkpoint.
        if version.current_log:
            minimum = int(Path(version.current_log).stem)
            names.update(p.name for p in folder.glob('*.log')
                         if p.stem.isdecimal() and int(p.stem) >= minimum)
        if len(names) > 512:
            raise ValueError('Too many cache files')
        hashes = {'CURRENT': hashlib.sha256(current).digest(),
                  manifest: hashlib.sha256(manifest_data).digest()}
        total = len(current) + len(manifest_data)
        for name in sorted(names):
            data = _read(folder, name)
            total += len(data)
            if total > MAX_TOTAL:
                raise ValueError('Cache exceeds supported size')
            hashes[name] = hashlib.sha256(data).digest()
            (target / name).write_bytes(data)
        for name, digest in reversed(list(hashes.items())):
            if hashlib.sha256(_read(folder, name)).digest() != digest:
                raise ValueError('Cache changed during snapshot')
        if {p.name for p in folder.glob('*.log') if p.stem.isdecimal()
                and (not version.current_log or int(p.stem) >= int(Path(version.current_log).stem))} - names:
            raise ValueError('Cache changed during snapshot')
        yield target, names


def read_current(database, state, progress):
    from native_leveldb import records_from_file
    from desktop_service import UserError
    try:
        account = account_directory(database)
        expected = account / 'WXWorkCefCache/Local Storage/leveldb'
        folder = expected.resolve(strict=True)
        if folder != expected:
            raise ValueError('Cache directory is redirected')
        progress('正在读取当前账号的会议文字缓存……')
        with stable_snapshot(folder, state) as (snapshot, names):
            records = (item for name in sorted(names)
                       for item in records_from_file(snapshot / name))
            return select_current(records, account.name)
    except FileNotFoundError:
        raise UserError('meeting_cache_missing', '未找到此账号的会议文字缓存。',
                        '请在企业微信内打开会议的智能纪要及文字记录，等待加载后刷新。无需浏览器登录或复制文字；清理缓存或换电脑后需要重新加载。') from None
    except Exception as error:
        if isinstance(error, UserError):
            raise
        raise UserError('meeting_cache_unreadable', '会议缓存暂时无法读取。',
                        '请等待企业微信加载完成后刷新。缓存变化、文件权限或客户端格式更新均可能导致此提示；不会导出读取失败的片段。') from None


def decode_meeting(code, raw):
    try:
        if not raw or raw[0] not in (0, 1):
            raise ValueError('Unsupported string encoding')
        envelope = json.loads(raw[1:].decode('utf-16le' if raw[0] == 0 else 'latin1'))
        if not isinstance(envelope, list) or len(envelope) < 5 or str(envelope[4]['meeting_code']) != code:
            raise ValueError('Meeting identity mismatch')
        data = envelope[1]
        info = data['base_info']['record_item']
        title = base64.b64decode(info['subject'], validate=True).decode('utf-8')
        started = int(info['begin_time'])
        datetime.fromtimestamp(started, ZONE)
        records, unresolved = [], {}
        groups = data['text_convert_list']['share_items']
        if not isinstance(groups, list):
            raise ValueError('Invalid transcript groups')
        for session, group in enumerate(groups, 1):
            start = datetime.fromtimestamp(int(group['record_start_time']), ZONE)
            if not isinstance(group['items'], list):
                raise ValueError('Invalid transcript entries')
            for item in group['items']:
                if len(records) >= 100000:
                    raise ValueError('Oversized transcript')
                text, name = item['content'], item['name']
                if not isinstance(text, str) or not isinstance(name, str):
                    raise ValueError('Invalid transcript text')
                offset = int(item['speak_time'])
                if offset < 0:
                    raise ValueError('Invalid timestamp')
                if not name:
                    uid = str(item['vid'])
                    name = unresolved.setdefault(uid, f'成员{len(unresolved) + 1}')
                records.append(dict(text=text, speaker=name, session=session,
                    time=(start + timedelta(milliseconds=offset)).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    offset_ms=offset, content_id=str(item['content_id'])))
        if not records or len(records) > 100000:
            raise ValueError('Empty or oversized transcript')
        result = dict(records=records, source_kind='meeting', server_completeness_verified=False,
                      cache_saved_at=envelope[2], missing_id_ranges=[], last_segment_ended=True,
                      unresolved_speakers=unresolved, excluded_nonzero_state=0)
        return title, result, started
    except (KeyError, TypeError, IndexError, OverflowError, OSError, UnicodeError) as error:
        raise ValueError('Unsupported meeting cache content') from error


class MeetingEngine:
    def catalog(self, database, state, progress):
        from desktop_service import UserError
        rooms = []
        for code, record in read_current(database, state, progress).items():
            try:
                title, result, started = decode_meeting(code, record.value)
            except ValueError:
                rooms.append(dict(room_id=code, title='缓存内容暂不可导出', started=0, unavailable=True))
                continue
            rooms.append(dict(room_id=code, title=title, started=started,
                              passages=len(result['records'])))
        return sorted(rooms, key=lambda room: room['started'], reverse=True)

    def extract(self, database, state, room_id, progress, **options):
        from desktop_service import UserError
        row = read_current(database, state, progress).get(room_id)
        if row is None:
            raise UserError('meeting_cache_missing', '此会议已不在当前缓存中。', '请在企业微信重新打开文字记录后刷新列表。')
        try:
            title, result, _ = decode_meeting(room_id, row.value)
        except ValueError:
            raise UserError('meeting_content_unsupported', '本条会议缓存尚无可读取的完整结构。',
                            '请在企业微信打开文字记录并等待加载后刷新；若仍失败，可能需要适配新的缓存格式。') from None
        return title, result
