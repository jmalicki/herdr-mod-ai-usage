#!/usr/bin/python3
"""Read subscription quotas through the installed CLIs. No prompts or credentials."""
import argparse
import concurrent.futures
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from compat import iso_timestamp

TTL = 300
TIMEOUT = 18


def timestamp(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        try:
            result = iso_timestamp(value)
        except ValueError:
            return None
    return result if math.isfinite(result) else None


def window(label, percent, reset):
    if isinstance(percent, bool):
        return None
    try:
        percent = float(percent)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        return None
    return dict(label=label, used=percent, resets_at=timestamp(reset))


def duration(minutes):
    if not minutes:
        return 'Window'
    if minutes % 1440 == 0:
        return f'{minutes // 1440}d'
    return f'{minutes // 60}h' if minutes % 60 == 0 else f'{minutes}m'


def codex_windows(body):
    buckets = body.get('rateLimitsByLimitId') or {'codex': body.get('rateLimits') or {}}
    rows = []
    for key, bucket in buckets.items():
        for field in ('primary', 'secondary'):
            data = bucket.get(field)
            if not isinstance(data, dict):
                continue
            label = duration(data.get('windowDurationMins'))
            if key != 'codex':
                label = f"{bucket.get('limitName') or key} · {label}"
            row = window(label, data.get('usedPercent'), data.get('resetsAt'))
            if row:
                rows.append(row)
    return rows


def claude_windows(body):
    raw = body.get('rate_limits') or {}
    names = {'five_hour': '5h', 'seven_day': '7d', 'seven_day_opus': 'Opus · 7d',
             'seven_day_sonnet': 'Sonnet · 7d', 'spend_limit': 'Spend'}
    rows = []
    for key, label in names.items():
        data = raw.get(key)
        if isinstance(data, dict):
            row = window(label, data.get('utilization', data.get('used_percentage')), data.get('resets_at'))
            if row:
                rows.append(row)
    for data in raw.get('model_scoped') or []:
        if isinstance(data, dict):
            row = window(f"{data.get('display_name', 'Model')} · 7d",
                         data.get('utilization', data.get('used_percentage')), data.get('resets_at'))
            if row:
                rows.append(row)
    return rows


def binary(name):
    override = os.environ.get(f'HERDR_USAGE_{name.upper()}_BIN')
    paths = [override, shutil.which(name), str(Path.home() / '.local/bin' / name),
             f'/opt/homebrew/bin/{name}', f'/usr/local/bin/{name}']
    for path in paths:
        if path and os.access(path, os.X_OK):
            return path
    raise RuntimeError(f'{name} is not installed')


class JsonProcess:
    """A bounded JSON-lines exchange; stderr never reaches the UI or cache."""
    def __init__(self, args, cwd):
        env = dict(os.environ, DISABLE_AUTOUPDATER='1', DISABLE_ERROR_REPORTING='1')
        env.pop('CLAUDECODE', None)
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, cwd=cwd, env=env,
                                        text=True, start_new_session=True)
        self.messages = queue.Queue()
        self.deadline = time.monotonic() + TIMEOUT
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    pass
        finally:
            self.messages.put(None)

    def send(self, obj):
        self.process.stdin.write(json.dumps(obj) + '\n')
        self.process.stdin.flush()

    def receive(self, predicate):
        while True:
            try:
                msg = self.messages.get(timeout=max(0, self.deadline - time.monotonic()))
            except queue.Empty:
                raise RuntimeError('Usage request timed out') from None
            if msg is None:
                raise RuntimeError('CLI closed before reporting usage')
            if isinstance(msg, dict) and predicate(msg):
                return msg

    def close(self):
        # Only the helper process group created above, never an existing agent.
        import signal
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self.process.pid, signal.SIGTERM)
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()


def fetch(name, state):
    if name in ('Gemini chat', 'Antigravity'):
        from google_api import fetch_antigravity, fetch_gemini
        data = fetch_gemini() if name == 'Gemini chat' else fetch_antigravity()
        data['windows'] = [dict(row, resets_at=timestamp(row.get('resets_at'))) for row in data['windows']]
        return data
    if name == 'Codex':
        args = [binary('codex'), 'app-server', '-c', 'mcp_servers={}', '-c', 'features.hooks=false']
    else:
        args = [binary('claude'), '-p', '--safe-mode', '--no-session-persistence',
                '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose']
    proc = JsonProcess(args, state)
    try:
        if name == 'Codex':
            proc.send(dict(id=1, method='initialize', params=dict(clientInfo=dict(
                name='herdr_usage', version='0.1.0'))))
            hello = proc.receive(lambda m: m.get('id') == 1)
            if 'error' in hello:
                raise RuntimeError('Codex initialization failed')
            proc.send(dict(method='initialized', params={}))
            proc.send(dict(id=2, method='account/rateLimits/read'))
            reply = proc.receive(lambda m: m.get('id') == 2)
            if 'error' in reply:
                raise RuntimeError('Codex usage unavailable; check codex login and connection')
            body = reply.get('result') or {}
            rows = codex_windows(body)
            plan = (body.get('rateLimits') or {}).get('planType')
        else:
            proc.send(dict(type='control_request', request_id='herdr-usage',
                           request=dict(subtype='get_usage', skip_behaviors=True)))
            reply = proc.receive(lambda m: m.get('type') == 'control_response'
                                 and (m.get('response') or {}).get('request_id') == 'herdr-usage')
            response = reply.get('response') or {}
            if response.get('subtype') != 'success':
                raise RuntimeError('Claude usage unavailable; check claude login and connection')
            body = response.get('response') or {}
            rows = claude_windows(body)
            plan = body.get('subscription_type')
        if not rows:
            raise RuntimeError('No subscription limits reported for this sign-in')
        return dict(name=name, windows=rows, plan=plan, observed_at=time.time(), error=None)
    finally:
        proc.close()


def read_cache(path):
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def collect_provider(name, state, force=False):
    path = state / f'{name.lower()}.json'
    with (state / f'{name.lower()}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = read_cache(path)
        now = time.time()
        # Even refresh clicks respect a short cooldown to avoid request floods.
        if now - old.get('checked_at', 0) < (30 if force else TTL):
            return old
        try:
            data = fetch(name, state)
        except Exception as exc:
            # Keep the last reading visible but clearly mark it stale/failed.
            data = dict(name=name, windows=old.get('windows', []),
                        observed_at=old.get('observed_at'), plan=old.get('plan'),
                        error=str(exc) if isinstance(exc, RuntimeError) else 'Could not read usage from CLI')
        data['checked_at'] = time.time()
        fd, temporary = tempfile.mkstemp(dir=state, prefix='.usage-')
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump(data, output)
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
        return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true')
    names = ['Codex', 'Claude', 'Gemini chat', 'Antigravity']
    parser.add_argument('--providers', nargs='*', choices=names, default=names)
    parser.add_argument('--state', type=Path, default=Path(os.environ.get(
        'HERDR_APP_HOME', str(Path.home() / '.config/herdr-app'))) / 'data/plan-usage')
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    def read_provider(name):
        if name in args.providers:
            return collect_provider(name, args.state, args.force)
        return read_cache(args.state / f'{name.lower()}.json') or dict(name=name, windows=[])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        providers = list(pool.map(read_provider, names))
    print(json.dumps(dict(providers=providers, generated_at=time.time())))


if __name__ == '__main__':
    main()
