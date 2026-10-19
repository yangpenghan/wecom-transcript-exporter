"""Build a portable release from an explicit source/data allowlist, never user state."""
import hashlib
from importlib import metadata
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'WeCom Transcript Exporter'
VERSION = '1.3.0'


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build this Windows release on Windows.')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
               '--name', NAME, '--distpath', str(ROOT / 'dist' / VERSION), '--workpath', str(ROOT / 'build'),
               '--specpath', str(ROOT / 'build'), '--add-data', str(ROOT / 'web') + ':web',
               '--add-data', str(ROOT / 'native_support/scan_voice_room_key.ps1') + ':native_support',
               str(ROOT / 'desktop_app.py')]
    subprocess.run(command, cwd=ROOT, check=True)
    package = ROOT / 'dist' / VERSION / NAME
    shutil.copy2(ROOT / 'docs/portable-guide.md', package / 'START-HERE.md')
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', package / 'THIRD_PARTY_NOTICES.md')
    for name in ('LICENSE', 'NOTICE', 'SECURITY.md'):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, package / name)
    notices = package / 'licenses'
    notices.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'native_support/LICENSE.wecom-agent', notices / 'LICENSE.wecom-agent')
    for name in ('cryptography', 'cffi', 'pycparser', 'pyinstaller'):
        distribution = metadata.distribution(name)
        for relative in distribution.files or []:
            if any(part.lower() in ('licenses', 'license', 'copying.txt') for part in relative.parts):
                source = Path(distribution.locate_file(relative))
                if source.is_file():
                    destination = notices / name / Path(*relative.parts[1:])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license, notices / 'LICENSE.python.txt')
    archive = ROOT / 'dist' / f'WeCom-Transcript-Exporter-{VERSION}-windows-x64.zip'
    forbidden = {'exports', '.native-state', '.local-archive', 'preferences.json', 'voice-room-key.dpapi'}
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for file in sorted(package.rglob('*')):
            if file.is_file():
                relative = file.relative_to(package)
                if forbidden.intersection(relative.parts) or file.suffix in ('.db', '.dpapi'):
                    raise RuntimeError('Private data must not be included in a portable package')
                output.write(file, Path(NAME) / relative)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(checksum + '  ' + archive.name + '\n', encoding='utf-8')
    print(f'Built {archive.name}: {archive.stat().st_size / 1048576:.1f} MiB')


if __name__ == '__main__':
    main()
