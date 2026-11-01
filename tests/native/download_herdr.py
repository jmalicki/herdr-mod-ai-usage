#!/usr/bin/env python3
"""Fetch checksum-verified official GUI/core releases into a CI-only directory."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tarfile

VERSION = '0.1.11'


def download(url):
    return subprocess.check_output(['curl', '--fail', '--silent', '--show-error',
                                    '--location', '--retry', '3', '--max-time', '180', url])


def main():
    root = Path(sys.argv[1]).resolve()
    system = {'Darwin': 'macos', 'Linux': 'linux'}[platform.system()]
    arch = {'arm64': 'aarch64', 'aarch64': 'aarch64', 'x86_64': 'x86_64'}[platform.machine()]
    for product in ('app', 'core'):
        base = f'https://releases.herdr.dev/{product}/{VERSION}'
        manifest = json.loads(download(base + '/manifest.json'))
        target = manifest['targets'][f'{system}-{arch}']
        assert target['url'].startswith(base + '/'), target
        data = download(target['url'])
        assert hashlib.sha256(data).hexdigest() == target['sha256'], 'Checksum mismatch'
        dest = root / product
        dest.mkdir(parents=True, exist_ok=True)
        archive = root / f'{product}.tar.gz'
        archive.write_bytes(data)
        with tarfile.open(archive) as package:
            for entry in package.getmembers():
                path = (dest / entry.name).resolve()
                if dest not in path.parents or entry.issym() or entry.islnk():
                    # macOS app bundles contain ordinary internal symlinks.
                    if entry.issym() and dest in (path.parent / entry.linkname).resolve().parents:
                        continue
                    raise ValueError(f'Unsafe archive entry: {entry.name}')
            package.extractall(dest)
        print(f'{product}: {manifest["version"]} {system}-{arch}', flush=True)


if __name__ == '__main__':
    main()
