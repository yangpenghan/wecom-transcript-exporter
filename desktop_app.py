"""Loopback-only browser application; also the windowless portable entry point."""
import argparse
import base64
import ctypes
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit
import uuid
import webbrowser

from desktop_service import DesktopService, UserError, explain_error

ROOT = Path(__file__).resolve().parent


def choose_location(kind):
    if kind not in ('database', 'search', 'output'):
        raise UserError('picker_kind', '无法识别所选位置类型。')
    from native_export import powershell
    # Fixed script only: no user path is interpolated into executable code.
    script = """
Add-Type -AssemblyName System.Windows.Forms
$owner=New-Object System.Windows.Forms.Form
$owner.TopMost=$true
$owner.ShowInTaskbar=$false
"""
    if kind == 'database':
        script += """
$dialog=New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title='选择企业微信面聊数据库'
$dialog.Filter='企业微信面聊数据库（voice_room5.db）|voice_room5.db'
$dialog.CheckFileExists=$true
$result=$dialog.ShowDialog($owner)
$selected=$dialog.FileName
"""
    else:
        script += """
$dialog=New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description='选择本地文件夹'
$dialog.UseDescriptionForTitle=$true
$result=$dialog.ShowDialog($owner)
$selected=$dialog.SelectedPath
""".replace('$dialog.UseDescriptionForTitle=$true\n', '')
    script += """
if($result -eq [System.Windows.Forms.DialogResult]::OK){
 [Console]::Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($selected)))
}
$dialog.Dispose()
$owner.Dispose()
"""
    result = powershell(['-STA', '-Command', script], 180)
    if result.returncode:
        raise UserError('picker_unavailable', '无法打开 Windows 位置选择窗口。', '请在位置输入框中粘贴完整的本地路径。')
    return {'path': base64.b64decode(result.stdout.strip()).decode('utf-8') if result.stdout.strip() else ''}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, service):
        super().__init__(('127.0.0.1', 0), LocalHandler)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.token = secrets.token_urlsafe(32)
        self.cookie_name = f'wecom_session_{self.server_port}'
        self.service = service
        self.jobs, self.guard = {}, threading.Lock()
        self.active = None
        self.last_seen = time.monotonic()

    def start_job(self, operation):
        with self.guard:
            if self.active:
                raise UserError('busy', '另一项操作仍在进行。', '请等待当前操作完成后再继续。')
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {'state': 'running', 'stage': '正在启动……'}
            self.active = job_id
            while len(self.jobs) > 20:
                del self.jobs[next(iter(self.jobs))]

        def run():
            def progress(stage):
                with self.guard:
                    self.jobs[job_id]['stage'] = stage
            try:
                result = operation(progress)
                update = {'state': 'done', 'result': result}
            except Exception as error:
                update = {'state': 'error', 'error': explain_error(error)}
            with self.guard:
                self.jobs[job_id].update(update)
                self.active = None
                self.last_seen = time.monotonic()
        threading.Thread(target=run, daemon=True).start()
        return job_id


class LocalHandler(BaseHTTPRequestHandler):
    server_version = 'LocalExporter'

    def log_message(self, *args):
        pass  # No URLs, paths, tokens or recording titles in access logs.

    def send_bytes(self, status, content, mime='application/json; charset=utf-8', extra=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status, obj, extra=None):
        self.send_bytes(status, json.dumps(obj, ensure_ascii=False).encode(), extra=extra)

    def valid_host(self):
        return self.headers.get('Host') == self.server.origin.removeprefix('http://')

    def authorized(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie[self.server.cookie_name].value if self.server.cookie_name in cookie else ''
            return secrets.compare_digest(token, self.server.token)
        except (ValueError, TypeError):
            return False

    def do_GET(self):
        if not self.valid_host() or self.headers.get('Origin', self.server.origin) != self.server.origin:
            return self.send_json(403, {'error': {'message': '请求来源无效，请从程序入口重新打开应用。'}})
        parsed = urlsplit(self.path)
        if parsed.path.startswith('/api/'):
            if not self.authorized():
                return self.send_json(401, {'error': {'message': '请从程序入口重新打开应用，以建立本地会话。'}})
            self.server.last_seen = time.monotonic()
            try:
                if parsed.path == '/api/health':
                    return self.send_json(200, self.server.service.health())
                if parsed.path == '/api/job':
                    job_id = parse_qs(parsed.query).get('id', [''])[0]
                    with self.server.guard:
                        job = dict(self.server.jobs.get(job_id, {}))
                    if not job:
                        raise UserError('job_missing', '此操作已失效。', '请重新执行此操作。')
                    return self.send_json(200, job)
                if parsed.path == '/api/download':
                    args = parse_qs(parsed.query)
                    file = self.server.service.output_file(args.get('id', [''])[0], args.get('kind', [''])[0])
                    return self.send_bytes(200, file.read_bytes(), 'application/octet-stream',
                                           {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(file.name)})
                return self.send_json(404, {'error': {'message': '无法识别此操作。'}})
            except Exception as error:
                return self.send_json(400, {'error': explain_error(error)})
        relative = unquote(parsed.path).lstrip('/') or 'index.html'
        directory = (ROOT / 'web').resolve()
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or path.suffix not in ('.html', '.css', '.js', '.svg', '.woff2', '.ico'):
            return self.send_json(404, {'error': {'message': '未找到所需资源。'}})
        mime = {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html'}.get(path.suffix) or mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        self.send_bytes(200, path.read_bytes(), mime)

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') != self.server.origin:
            return self.send_json(403, {'error': {'message': '请求来源无效，请从程序入口重新打开应用。'}})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 16384:
                return self.send_json(413, {'error': {'message': '请求内容过大。'}})
            data = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            return self.send_json(400, {'error': {'message': '请求格式无效。'}})
        path = urlsplit(self.path).path
        if path == '/api/session':
            supplied = data.get('token', '')
            if not isinstance(supplied, str) or not secrets.compare_digest(supplied, self.server.token):
                return self.send_json(401, {'error': {'message': '会话已失效，请重新打开应用。'}})
            return self.send_json(200, {'ready': True}, {'Set-Cookie': self.server.cookie_name + '=' + self.server.token + '; HttpOnly; SameSite=Strict; Path=/'})
        if not self.authorized():
            return self.send_json(401, {'error': {'message': '请从程序入口重新打开应用。'}})
        self.server.last_seen = time.monotonic()
        service = self.server.service
        try:
            if path == '/api/heartbeat':
                return self.send_json(200, {'alive': True})
            operations = {
                '/api/discover': lambda p: service.discover(str(data.get('root', ''))),
                '/api/browse': lambda p: choose_location(data.get('kind')),
                '/api/connect': lambda p: service.connect(str(data.get('path', '')), data.get('consent') is True, p),
                '/api/export': lambda p: service.export(str(data.get('room_id', '')), str(data.get('folder', '')), p),
                '/api/revoke': lambda p: service.revoke(),
            }
            if path in operations:
                return self.send_json(202, {'job': self.server.start_job(operations[path])})
            if path == '/api/open-folder':
                file = service.output_file(str(data.get('id', '')), 'md')
                os.startfile(str(file.parent))
                return self.send_json(200, {'opened': True})
            if path == '/api/exit':
                if self.server.active:
                    raise UserError('busy', '请等待当前操作完成后再退出。')
                self.send_json(200, {'closed': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self.send_json(404, {'error': {'message': '无法识别此操作。'}})
        except Exception as error:
            return self.send_json(400, {'error': explain_error(error)})


def create_server(service=None):
    return LocalServer(service or DesktopService())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true', help='For local integration tests')
    parser.add_argument('--session-file', type=Path, help='Private local integration-test connection file')
    parser.add_argument('--state-dir', type=Path, help='Isolated local state for testing')
    args = parser.parse_args()
    server = create_server(DesktopService(args.state_dir))
    launch = server.origin + '/#' + server.token
    if args.session_file:
        args.session_file.parent.mkdir(parents=True, exist_ok=True)
        args.session_file.write_text(json.dumps({'url': launch, 'pid': os.getpid()}), encoding='utf-8')
    if not args.no_browser:
        if not webbrowser.open(launch):
            ctypes.windll.user32.MessageBoxW(None, '请在浏览器中打开以下本地地址：\n\n' + launch, '企微面聊导出', 0)

    def idle_shutdown():
        while True:
            time.sleep(10)
            if not server.active and time.monotonic() - server.last_seen > 180:
                server.shutdown()
                return
    threading.Thread(target=idle_shutdown, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        if args.session_file:
            args.session_file.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        if os.name == 'nt':
            ctypes.windll.user32.MessageBoxW(None, '应用未能启动。请将完整便携 ZIP 解压到可写入的本地文件夹后重试。源码版请先运行 Setup.cmd。如受组织策略限制，请联系 IT。', '企微面聊导出', 0x10)
        raise
