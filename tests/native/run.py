#!/usr/bin/env python3
"""Exercise the release ZIP in a real, isolated Herdr window (no accounts)."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile

PROJECT = Path(__file__).resolve().parents[2]


def wait_for(description, check, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError, subprocess.SubprocessError, KeyError):
            pass
        time.sleep(.25)
    raise AssertionError('Timed out: ' + description)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--herdr', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=PROJECT / 'native-results')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    binaries = args.herdr.resolve()
    app = next(binaries.glob('app/**/Contents/MacOS/Herdr'), None)
    app = app or next(path for path in binaries.glob('app/**/herdr-app') if path.is_file())
    core = next(binaries.glob('core/**/hc'), None)
    core = core or next(binaries.glob('core/**/herdr-core'))
    # Short, private paths keep UNIX socket addresses below macOS's limit.
    with tempfile.TemporaryDirectory(prefix='usage-', dir='/tmp') as temporary:
        root = Path(temporary)
        home = root / 'app'
        home.mkdir()
        (root / 'user').mkdir()
        (root / 'bin').mkdir()
        (root / 'run').mkdir(mode=0o700)
        (root / 'bin/herdr-app').symlink_to(app)
        (root / 'bin/hc').symlink_to(core)
        env = dict(os.environ, HOME=str(root / 'user'), HERDR_APP_HOME=str(home),
                   XDG_CONFIG_HOME=str(root / 'config'), XDG_STATE_HOME=str(root / 'state'),
                   XDG_RUNTIME_DIR=str(root / 'run'),
                   HC_SESSION='usage-' + root.name, HERDR_APP_NO_SOUND='1',
                   HERDR_TELEMETRY='0', HERDR_RELEASES_URL='http://127.0.0.1:1',
                   PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'])
        for key in ('HC_SOCKET', 'HC_TERMINAL_ID', 'HC_TERMINAL_SOCKET', 'HC_SCOPE'):
            env.pop(key, None)
        (home / 'settings.json').write_text(json.dumps(dict(core=str(core), zoom=1, telemetry=False)))
        (home / 'shared.json').write_text(json.dumps({'frame.welcomed': 'skipped'}))
        (home / 'window.json').write_text(json.dumps(dict(state='windowed', bounds=[0, 0, 1100, 820])))
        state = home / 'data/plan-usage'
        state.mkdir(parents=True)
        now = time.time()
        for name in ('Codex', 'Claude', 'Gemini chat', 'Antigravity'):
            data = dict(name=name, observed_at=now, checked_at=now + 86400,
                        windows=[dict(label='5h', used=37, resets_at=now + 7200),
                                 dict(label='7d', used=64, resets_at=now + 86400)])
            (state / (name.lower() + '.json')).write_text(json.dumps(data))

        def command(*words):
            completed = subprocess.run([str(app), *words], env=env, capture_output=True,
                                       text=True, timeout=15, check=True)
            if words[0] == 'shot':
                return completed.stdout
            return json.loads(completed.stdout) if completed.stdout.strip() else {}

        def do(name, **values):
            return command('do', name, json.dumps(values))

        def shared():
            return json.loads((home / 'shared.json').read_text())

        def panel():
            report = shared().get('ci.panel', {})
            assert not report.get('error'), report
            assert not command('status').get('errors'), command('status')
            return report

        def screenshot(name):
            path = output / (name + '.png')
            command('shot', str(path))
            assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and path.stat().st_size > 5000

        process = None
        log = (output / 'app.log').open('w')
        try:
            subprocess.run([str(core), 'server', 'start'], env=env, check=True, timeout=30,
                           stdout=log, stderr=log)
            process = subprocess.Popen([str(app)], env=env, stdout=log, stderr=log,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            wait_for('native app startup', lambda: command('status'))
            subprocess.run([sys.executable, str(PROJECT / 'build_release.py'), '--output', str(root / 'dist')], check=True)
            with zipfile.ZipFile(next((root / 'dist').glob('*.zip'))) as archive:
                archive.extractall(root / 'release')
            release = next((root / 'release').iterdir())
            subprocess.run([sys.executable, str(release / 'install.py')], env=env, check=True, timeout=60)
            wait_for('usage layout', lambda: command('status').get('layout') == 'usage')
            # Observe the real shipped view through a test-only subclass. No test
            # command or instrumentation is included in the distributed mod.
            mod = home / 'mods/plan-usage'
            (mod / 'main.js').rename(mod / 'production.js')
            shutil.copy2(PROJECT / 'tests/native/probe.js', mod / 'main.js')
            loaded = wait_for('helper output rendered by native view', lambda:
                              panel() if panel().get('data') and not panel().get('busy') else None)
            assert [p['name'] for p in loaded['data']['providers']] == ['Codex', 'Claude', 'Gemini chat', 'Antigravity']
            assert loaded['data']['providers'][0]['windows'][0]['used'] == 37
            screenshot('panel-wide')
            do('layout.resize', id='sidebar', px=220)
            wait_for('narrow responsive panel', lambda: 0 < panel().get('width', 0) < 240)
            screenshot('panel-narrow')
            do('layout.resize', id='sidebar', px=320)
            wait_for('wide responsive panel', lambda: panel().get('width', 0) >= 240)
            do('layout.resize', id='plan-usage-panel', px=180)
            wait_for('manual panel resizing', lambda: abs(panel().get('height', 0) - 180) < 3)
            wait_for('manual resize disables automatic fit', lambda:
                     shared()['plan-usage.preferences']['autoFit'] is False)
            do('plan-usage.fit')
            wait_for('automatic fit restored', lambda:
                     shared()['plan-usage.preferences']['autoFit'] and panel().get('height', 0) > 180)
            do('plan-usage.settings')
            wait_for('native settings overlay', lambda: 'plan-usage' in command('status').get('overlays', []))
            wait_for('settings view rendered', lambda: shared().get('ci.settings', {}).get('settings'))
            screenshot('settings')
            status = command('status')
            assert not status['errors'], status
            (output / 'status.json').write_text(json.dumps(status, indent=2))
            (output / 'observations.json').write_text(json.dumps(shared(), indent=2))
            print('PASS: installed release, native rendering, cached quotas, responsive width, manual resize, auto-fit and settings', flush=True)
        finally:
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            subprocess.run([str(core), 'server', 'stop'], env=env, capture_output=True, timeout=15)
            for name in ('shared.json', 'settings.error', 'layout.error'):
                if (home / name).exists():
                    shutil.copy2(home / name, output / name)
            log.close()


if __name__ == '__main__':
    main()
