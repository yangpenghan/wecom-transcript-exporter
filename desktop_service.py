"""User-scoped discovery, access and export operations for the local interface."""
import contextlib
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from collections import deque
import re
import sqlite3
import tempfile
import time
import uuid


class UserError(Exception):
    def __init__(self, code, message, action=''):
        super().__init__(message)
        self.code, self.message, self.action = code, message, action

    def as_dict(self):
        return dict(code=self.code, message=self.message, action=self.action)


def documents_folder():
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                return Path(os.path.expandvars(winreg.QueryValueEx(key, 'Personal')[0]))
        except OSError:
            pass
    return Path.home() / 'Documents'


def local_state_folder():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'WeComTranscriptExporter'


def process_running(pid):
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if handle:
        kernel.CloseHandle(handle)
        return True
    return ctypes.get_last_error() != 87  # Access denied/unknown means keep it.


def clean_abandoned_snapshots(state):
    """Only known files in a dead process's app-owned snapshot; never recurse."""
    root = Path(state).resolve()
    for directory in (root / 'profiles').glob('*/snapshot-*'):
        match = re.fullmatch(r'snapshot-(\d+)-[a-zA-Z0-9_-]+', directory.name)
        if not match or process_running(int(match[1])):
            continue
        if directory.is_symlink() or (hasattr(directory, 'is_junction') and directory.is_junction()):
            continue
        if not directory.resolve().is_relative_to(root):
            continue
        try:
            for file in directory.iterdir():
                if file.name == 'voice-room.db' or (file.name.startswith('.wecom-') and file.suffix in ('.tmp', '.db')):
                    if file.is_file() and not file.is_symlink():
                        file.unlink()
            directory.rmdir()
        except OSError:
            pass


def default_roots():
    folders = [documents_folder(), Path.home() / 'Documents']
    for name in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
        if os.environ.get(name):
            folders.append(Path(os.environ[name]) / 'Documents')
    return [folder / name / 'Profiles' for folder in folders for name in ('WXWork', 'WeCom')]


def validate_database_path(value):
    path = Path(str(value).strip().strip('"')).expanduser()
    if str(path).startswith(('\\\\', '//')):
        raise UserError('local_database_required', '请选择本机上的数据库。', '请选择本地磁盘中的文件，暂不支持网络共享位置。')
    try:
        path = path.resolve(strict=True)
        if path.name.lower() != 'voice_room5.db' or not path.is_file():
            raise UserError('wrong_file', '所选文件不是面聊数据库。', '请选择企业微信账号文件夹内的 voice_room5.db。')
        with path.open('rb') as handle:
            page = handle.read(4096)
        if len(page) != 4096 or page[16:24] != bytes.fromhex('1000020200402020'):
            raise UserError('unsupported_database', '暂不支持此数据库格式。', '请使用 Windows 企业微信的原始 voice_room5.db 文件。新版客户端可能需要更新适配。')
    except FileNotFoundError:
        raise UserError('database_missing', '所选数据库已不在此位置。', '请登录企业微信，然后自动查找或重新选择当前数据位置。') from None
    except PermissionError:
        raise UserError('database_permission', 'Windows 未允许读取此数据库。', '请使用自己的 Windows 账号及企业微信数据。如组织限制读取，请联系 IT。') from None
    return path


def discover_databases(roots, max_directories=2500, max_depth=6):
    found, seen = {}, set()
    queue = deque((Path(p).expanduser(), 0) for p in roots)
    scanned, errors, entries = 0, 0, 0
    deadline, truncated = time.monotonic() + 4, False
    while queue:
        if scanned >= max_directories or entries >= 10000 or time.monotonic() >= deadline:
            truncated = True
            break
        path, depth = queue.popleft()
        try:
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            direct = path if path.name.lower() == 'voice_room5.db' else path / 'voice_room5.db'
            if direct.is_file():
                info = direct.stat()
                absolute = str(direct.resolve())
                found[absolute] = dict(path=absolute, profile=direct.parent.name, modified=info.st_mtime, size=info.st_size)
                # A profile's media tree cannot contain another account cache.
                # Never enumerate it after finding the profile's database.
                scanned += 1
                continue
            if not path.is_dir():
                continue
            scanned += 1
            with os.scandir(path) as children:
                for child in children:
                    entries += 1
                    if entries >= 10000 or time.monotonic() >= deadline:
                        truncated = True
                        break
                    if child.is_dir(follow_symlinks=False):
                        if depth < max_depth:
                            queue.append((Path(child.path), depth + 1))
                        else:
                            truncated = True
            if entries >= 10000 or time.monotonic() >= deadline:
                break
        except (OSError, RuntimeError):
            errors += 1
    return dict(candidates=sorted(found.values(), key=lambda p: p['modified'], reverse=True),
                truncated=truncated, unreadable_folders=errors, scanned_folders=scanned)


def explain_error(error):
    if isinstance(error, UserError):
        return error.as_dict()
    text = str(error)
    if isinstance(error, PermissionError):
        return UserError('permission_denied', 'Windows 阻止了对所需文件或进程的读取。', '请使用自己的账号和可写入的本地文件夹，避免使用另一管理员账号运行企业微信。如受组织策略限制，请联系 IT。').as_dict()
    if 'one WeCom desktop instance' in text:
        return UserError('wecom_not_ready', '首次连接需要找到一个匹配的企业微信进程。', '请打开企业微信并登录自己的账号，关闭额外启动的主程序，保持后台运行后重试。').as_dict()
    if 'key' in text.lower() or 'process' in text.lower():
        return UserError('local_access_failed', '本地读取检查未能验证此数据库。', '请确认所选数据属于当前登录账号，正常重启企业微信后重试。客户端更新、权限级别不同或组织策略可能阻止读取；应用不会请求管理员权限。').as_dict()
    if 'changed during snapshot' in text:
        return UserError('database_busy', '读取过程中，企业微信更新了缓存。', '请等待同步或录音结束后重试。').as_dict()
    if isinstance(error, (sqlite3.Error, ValueError)):
        return UserError('unsupported_content', '当前版本无法读取这些缓存数据。', '请在企业微信中重新打开记录后重试。如仍失败，可能是客户端格式已变化。应用不会将读取不完整的结果标记为完整记录。').as_dict()
    if isinstance(error, OSError):
        return UserError('file_operation_failed', '未能完成文件操作。', '请检查剩余磁盘空间，并选择可写入的本地 NTFS 文件夹。网络磁盘及部分移动存储不支持此导出方式。').as_dict()
    return UserError('operation_failed', '本次操作未完成。', '请重试。如仍失败，请重新打开应用并查看使用指南。').as_dict()


class NativeEngine:
    @contextlib.contextmanager
    def snapshot(self, database, state, progress):
        from native_export import database_key
        from native_support.wxwork_crypto import decrypt_database
        progress('正在检查本地读取权限，首次检查可能需要约一分钟……')
        key, _ = database_key(database, state)
        progress('正在读取并校验本地面聊缓存……')
        with tempfile.TemporaryDirectory(prefix=f'snapshot-{os.getpid()}-', dir=state) as directory:
            plain = Path(directory) / 'voice-room.db'
            decrypt_database(database, plain, key)
            with contextlib.closing(sqlite3.connect(plain.as_uri() + '?mode=ro&immutable=1', uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                yield conn

    def catalog(self, database, state, progress):
        from native_transcript import room_catalog
        with self.snapshot(database, state, progress) as conn:
            return room_catalog(conn)

    def extract(self, database, state, room_id, progress, resolve_speakers=False):
        from native_transcript import extract_room, room_catalog
        with self.snapshot(database, state, progress) as conn:
            room = next((r for r in room_catalog(conn) if str(r['room_id']) == room_id), None)
            if room is None:
                raise UserError('recording_moved', '所选缓存中已找不到这条面聊记录。', '请刷新列表后重新选择记录。')
            result = extract_room(conn, int(room_id))
            if resolve_speakers:
                from native_contacts import resolve_names
                names, report = resolve_names(database, state, result['unresolved_speakers'], progress)
                if names:
                    result = extract_room(conn, int(room_id), names)
                result['speaker_resolution'] = report
            return room['title'], result


class DesktopService:
    def __init__(self, state=None, engine=None, roots=None):
        self.state = Path(state) if state else local_state_folder()
        self.state.mkdir(parents=True, exist_ok=True)
        clean_abandoned_snapshots(self.state)
        self.config_path = self.state / 'preferences.json'
        try:
            self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
            if not isinstance(self.config, dict):
                self.config = {}
        except (OSError, ValueError):
            self.config = {}
        self.engine = engine or NativeEngine()
        self.roots = list(roots) if roots is not None else default_roots()
        self.database, self.rooms, self.outputs = None, [], {}

    def save(self):
        from native_support.local_io import atomic_output
        with atomic_output(self.config_path) as stream:
            json.dump(self.config, stream, ensure_ascii=False, indent=2)

    def has_consent(self, path):
        return str(Path(path).resolve()) in self.config.get('consented_databases', [])

    def health(self):
        shell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        return dict(windows=os.name == 'nt', crypto=importlib.util.find_spec('cryptography') is not None,
                    powershell=shell.is_file(), saved_database=self.config.get('database', ''),
                    output_folder=self.config.get('output_folder', str(documents_folder() / 'WeCom Exports')),
                    consented_databases=self.config.get('consented_databases', []),
                    tested_version='5.0.12.6018')

    def discover(self, root=''):
        roots = [root] if root else self.roots + ([self.config['database']] if self.config.get('database') else [])
        if root and not Path(root).exists():
            raise UserError('location_missing', '此位置不存在。', '请选择文件夹，或粘贴完整的本地路径。')
        if root and str(root).startswith(('\\\\', '//')):
            raise UserError('local_database_required', '请在本机文件夹中查找。', '请选择企业微信的本地存储文件夹。')
        return discover_databases(roots)

    def profile_state(self, database):
        folder = self.state / 'profiles' / hashlib.sha256(str(database).encode()).hexdigest()[:16]
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def connect(self, path, consent, progress):
        self.database, self.rooms = None, []
        database = validate_database_path(path)
        if not (consent is True or self.has_consent(str(database))):
            raise UserError('consent_required', '连接前，请先允许读取本地数据。', '请阅读授权说明并勾选同意，无需企业接口授权。')
        rooms = self.engine.catalog(database, self.profile_state(database), progress)
        # Native room IDs exceed JavaScript's safe integer range.
        self.rooms = [dict(room, room_id=str(room['room_id'])) for room in rooms]
        self.database = database
        allowed = set(self.config.get('consented_databases', []))
        allowed.add(str(database))
        self.config.update(database=str(database), consented_databases=sorted(allowed))
        self.save()
        return dict(rooms=self.rooms, database=str(database))

    def revoke(self):
        self.database, self.rooms = None, []
        self.config.pop('consented_databases', None)
        clean_abandoned_snapshots(self.state)
        # Remove only this app's known DPAPI key files, never source databases.
        for key in (self.state / 'profiles').glob('*/voice-room-key.dpapi'):
            key.unlink(missing_ok=True)
        self.save()
        return {'revoked': True}

    def export(self, room_id, destination, progress, resolve_speakers=False):
        if not self.database or not any(r['room_id'] == room_id for r in self.rooms):
            raise UserError('choose_recording', '请从当前列表中选择一条面聊记录。', '请连接数据库后选择面聊记录。')
        folder = Path(destination).expanduser()
        if not str(destination).strip() or str(folder).startswith(('\\\\', '//')):
            raise UserError('output_folder', '请选择本地导出文件夹。', '请选择本地 NTFS 磁盘中可写入的文件夹。')
        folder = folder.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder):
            pass
        began = time.perf_counter()
        options = {'resolve_speakers': True} if resolve_speakers else {}
        title, result = self.engine.extract(self.database, self.profile_state(self.database), room_id, progress, **options)
        progress('正在保存 Markdown 和 JSON……')
        from native_support.local_io import atomic_output
        from native_transcript import render_markdown
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:70] or 'Recording'
        if clean.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            clean = 'Recording-' + clean
        export_id = uuid.uuid4().hex
        base = folder / (clean + '-' + time.strftime('%Y%m%d-%H%M%S') + '-' + export_id[:6])
        md, js = Path(str(base) + '.md'), Path(str(base) + '.json')
        result.update(title=title, elapsed_seconds=round(time.perf_counter() - began, 3))
        with atomic_output(js, overwrite=False) as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        with atomic_output(md, overwrite=False, newline='\n') as stream:
            stream.write(render_markdown(title, result))
        self.outputs[export_id] = {'md': md, 'json': js}
        self.config['output_folder'] = str(folder)
        self.save()
        warnings = []
        if result.get('speaker_resolution', {}).get('status') == 'unavailable':
            warnings.append('本地通讯录暂时无法读取，已保留原成员编号。请确认企业微信仍已登录；复制或迁移过的数据可能缺少账号信息。')
        if result['missing_id_ranges']:
            warnings.append('本地缓存中存在消息编号缺口。请在企业微信中重新打开记录并刷新，确认内容是否完整。')
        if not result['last_segment_ended']:
            warnings.append('未找到最后一次录音结束标记，记录可能尚未同步完整或仍在录制。')
        if result['unresolved_speakers']:
            warnings.append('部分成员姓名缺失，已使用固定的成员编号标注。')
        if result['excluded_nonzero_state']:
            warnings.append(f"{result['excluded_nonzero_state']} 条非零状态文本记录已排除，详情请查看 JSON 报告。")
        return dict(id=export_id, title=title, passages=len(result['records']), elapsed=result['elapsed_seconds'],
                    folder=str(folder), markdown=md.name, json=js.name, warnings=warnings,
                    preview=result['records'][:30], preview_truncated=len(result['records']) > 30,
                    speaker_resolution=result.get('speaker_resolution', {'status': 'not_requested', 'resolved': 0}))

    def output_file(self, export_id, kind):
        path = self.outputs.get(export_id, {}).get(kind)
        if path is None or not path.is_file():
            raise UserError('output_missing', '当前应用会话无法访问此导出文件。', '请重新导出，或直接到保存文件夹打开已有文件。')
        return path
