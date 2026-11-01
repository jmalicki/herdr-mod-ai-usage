"""Google quota endpoints. Authentication stays in memory; only quota data is cached."""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from compat import iso_timestamp


def decrypt_cookie(ciphertext, key):
    """AES-CBC with PKCS#7 via macOS CommonCrypto; no Python/Node packages."""
    if len(key) != 16 or not ciphertext or len(ciphertext) % 16:
        raise RuntimeError('Invalid Chrome encrypted cookie')
    try:
        crypt = ctypes.CDLL('/usr/lib/libSystem.B.dylib').CCCrypt
    except (OSError, AttributeError):
        raise RuntimeError('Chrome session decryption requires macOS CommonCrypto') from None
    crypt.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                      ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                      ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                      ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    crypt.restype = ctypes.c_int
    key_buffer = ctypes.create_string_buffer(key)
    iv = ctypes.create_string_buffer(b' ' * 16)
    data = ctypes.create_string_buffer(ciphertext)
    output = ctypes.create_string_buffer(len(ciphertext) + 16)
    length = ctypes.c_size_t()
    # kCCDecrypt=1, kCCAlgorithmAES=0, kCCOptionPKCS7Padding=1.
    status = crypt(1, 0, 1, key_buffer, len(key), iv, data, len(ciphertext),
                   output, len(output), ctypes.byref(length))
    if status:
        raise RuntimeError('Chrome Google session could not be decrypted')
    return output.raw[:length.value]


class GoogleAPI:
    def __init__(self):
        self.deadline = time.monotonic() + 17

    def request(self, url, body=None, headers=None, form=False):
        if not url.startswith(('https://gemini.google.com/', 'https://oauth2.googleapis.com/',
                               'https://cloudcode-pa.googleapis.com/', 'https://daily-cloudcode-pa.googleapis.com/')):
            raise RuntimeError('Unexpected Google API destination')
        payload = None if body is None else (urllib.parse.urlencode(body) if form else json.dumps(body)).encode()
        headers = dict(headers or {})
        if payload is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        request = urllib.request.Request(url, data=payload, headers=headers)
        # Do not forward authentication headers to a redirect destination.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(
                    request, timeout=max(0.1, min(8, self.deadline - time.monotonic()))) as response:
                raw = response.read(2 * 1024 * 1024).decode()
            return json.loads(re.sub(r"^\s*\)\]\}'\s*", '', raw))
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308, 401, 403):
                raise RuntimeError('Google session unavailable; sign in again') from None
            if exc.code == 429:
                raise RuntimeError('Google rate limited this quota check; retry later') from None
            raise RuntimeError(f'Google quota API returned HTTP {exc.code}') from None
        except (OSError, ValueError):
            raise RuntimeError('Google quota API could not be reached or its response changed') from None


def fraction(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and 0 <= value <= 1 else None


def gemini_rows(payload):
    results = payload if isinstance(payload, list) else [payload]
    for result in results:
        viewer = (result.get('data') or {}).get('viewer') if isinstance(result, dict) else None
        if not isinstance(viewer, dict):
            continue
        info = (viewer.get('rpcs') or {}).get('getUsageInfo') or {}
        rows = []
        for pool in info.get('pools') or []:
            label = {'GXU_FIVE_HOURLY': '5h', 'GXU_WEEKLY': '7d'}.get(pool.get('poolType'))
            used = fraction(pool.get('percentageUsed'))
            if label and used is not None:
                rows.append(dict(label=label, used=used * 100,
                                 resets_at=(pool.get('gxu') or {}).get('windowRefreshesAt')))
        if rows:
            return rows, info.get('subscriptionTier')
    raise RuntimeError('Gemini chat returned no measured usage; check browser sign-in')


def antigravity_rows(payload):
    body = payload.get('response') or payload
    rows = []
    for group in body.get('groups') or []:
        for bucket in group.get('buckets') or []:
            if bucket.get('disabled'):
                continue
            remaining = bucket.get('remaining') or {}
            value = remaining.get('remainingFraction', bucket.get('remainingFraction'))
            if remaining.get('case') == 'remainingFraction':
                value = remaining.get('value')
            left = fraction(value)
            if left is None:
                continue
            group_name = group.get('displayName') or group.get('name') or 'Models'
            group_name = {'Gemini Models': 'Gemini', 'Claude and GPT models': 'Claude/GPT'}.get(group_name, group_name)
            label = bucket.get('displayName') or bucket.get('bucketId') or 'Window'
            label = {'Weekly Limit Remaining': '7d', 'Five Hour Limit Remaining': '5h'}.get(label, label)
            rows.append(dict(label=f'{group_name} · {label}', used=(1 - left) * 100,
                             resets_at=bucket.get('resetTime'), description=bucket.get('description')))
    if not rows:
        raise RuntimeError('Antigravity returned no measured quota summary')
    return rows


def chrome_cookie():
    """Read only Google-domain session rows from one explicit Chrome profile."""
    override = os.environ.get('HERDR_USAGE_GEMINI_COOKIE_FILE')
    if override:
        try:
            path = Path(override).expanduser()
            if path.stat().st_mode & 0o077:
                raise RuntimeError('Gemini Cookie header file must have permissions 600')
            value = path.read_text().strip()
            if not value or '\n' in value or '\r' in value:
                raise RuntimeError('Gemini Cookie header file is empty or invalid')
            return value
        except OSError:
            raise RuntimeError('Configured Gemini Cookie header file is not readable') from None
    root = Path.home() / 'Library/Application Support/Google/Chrome'
    profile = os.environ.get('HERDR_USAGE_CHROME_PROFILE', 'Default')
    if not re.fullmatch(r'Default|Profile [0-9]+', profile):
        raise RuntimeError('Invalid Chrome profile name')
    path = root / profile / 'Cookies'
    if not path.exists():
        path = root / profile / 'Network/Cookies'
    try:
        # Opening read-only also avoids copying any browser database into our cache.
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1) as conn:
            rows = conn.execute("select host_key,name,value,encrypted_value from cookies "
                                "where host_key in ('.google.com','gemini.google.com','.gemini.google.com') "
                                "and (expires_utc=0 or expires_utc>?)",
                                ((time.time() + 11644473600) * 1000000,)).fetchall()
    except (OSError, sqlite3.Error):
        raise RuntimeError('Chrome session access blocked by macOS; see project README') from None
    if not rows:
        raise RuntimeError('Sign in at gemini.google.com in the selected Chrome profile')
    key = None
    cookies = []
    for host, name, value, encrypted in rows:
        if not value and encrypted:
            if not encrypted.startswith(b'v10'):
                continue
            if key is None:
                try:
                    result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-w', '-s', 'Chrome Safe Storage'],
                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4, check=True)
                except (OSError, subprocess.SubprocessError):
                    raise RuntimeError('Could not read Chrome Google session from Keychain') from None
                key = hashlib.pbkdf2_hmac('sha1', result.stdout.rstrip(b'\n'), b'saltysalt', 1003, 16)
            plain = decrypt_cookie(encrypted[3:], key)
            host_hash = hashlib.sha256(host.encode()).digest()
            if plain.startswith(host_hash):
                plain = plain[32:]
            try:
                value = plain.decode('utf-8')
            except UnicodeDecodeError:
                raise RuntimeError('Chrome Google session could not be decoded') from None
        if value and '\r' not in value and '\n' not in value:
            cookies.append(f'{name}={value}')
    if not cookies:
        raise RuntimeError('No supported Google session cookies found in Chrome')
    return '; '.join(cookies)


def fetch_gemini():
    cookie = chrome_cookie()
    api = GoogleAPI()
    query = urllib.parse.urlencode(dict(
        query_signature='2/dWbCvkVB0X16r9NPnxifeOAAqdCqMf0xeWvau9yPy7g=',
        variables=json.dumps(dict(g1Request=dict(entrypoints=['GEMINI_USAGE_SETTINGS_UPGRADE_BANNER']),
                                  workspaceRequest=dict(recommendationsForSurfaceRequests=[])), separators=(',', ':'))))
    payload = api.request('https://gemini.google.com/_/BardChatUi/graphql/schemas/GEMINI_WEB_GRAPHQL/executeQuery?' + query,
                          headers={'Cookie': cookie, 'Accept': 'application/json', 'Referer': 'https://gemini.google.com/usage'})
    rows, plan = gemini_rows(payload)
    return dict(name='Gemini chat', windows=rows, plan=plan, observed_at=time.time(), error=None)


def oauth_client(binary):
    """Resolve paired public installed-app OAuth constants, never user credentials."""
    data = binary.read_bytes()
    def word(offset):
        return struct.unpack_from('<I', data, offset)[0]
    def reference(offset):
        page, add, length = word(offset), word(offset + 4), word(offset + 8)
        if page & 0x9f00001f != 0x90000001 or add & 0xffc003ff != 0x91000021 or length & 0xffe0001f != 0xd2800002:
            return None
        immediate = ((page >> 5) & 0x7ffff) * 4 + ((page >> 29) & 3)
        signed = immediate if immediate < 1 << 20 else immediate - (1 << 21)
        address = (offset & ~4095) + signed * 4096 + ((add >> 10) & 4095)
        count = (length >> 5) & 0xffff
        if address < 0 or address + count > len(data):
            return None
        return data[address:address + count].decode('ascii', errors='replace')
    preferred = '1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com'
    clients = []
    for match in re.finditer(re.escape(bytes.fromhex('010800a9')), data):
        pos = match.start() - 12
        if pos < 0 or pos % 4 or pos + 32 > len(data) or word(pos + 28) != 0xa9010801:
            continue
        client, secret = reference(pos), reference(pos + 16)
        if client and secret and re.fullmatch(r'[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com', client) and re.fullmatch(r'GOCSPX-[A-Za-z0-9_-]{28}', secret):
            clients.append((client, secret))
    for client in clients:
        if client[0] == preferred:
            return client
    if len(clients) == 1:
        return clients[0]
    raise RuntimeError('Could not resolve Antigravity OAuth client; update Antigravity')


def fetch_antigravity():
    api = GoogleAPI()
    path = Path.home() / '.gemini/jetski-standalone-oauth-token'
    try:
        saved = json.loads(path.read_text())
        token = saved.get('token') or {}
    except (OSError, ValueError):
        raise RuntimeError('Sign in to Antigravity on this computer') from None
    access = token.get('access_token')
    expiry = token.get('expiry')
    if not access:
        raise RuntimeError('Antigravity sign-in has no access token')
    if expiry and iso_timestamp(expiry) < time.time() + 60:
        binaries = [Path('/Applications/Development/Antigravity.app/Contents/Resources/bin/language_server'),
                    Path('/Applications/Antigravity.app/Contents/Resources/bin/language_server')]
        binary = next((b for b in binaries if b.exists()), None)
        if binary is None or not token.get('refresh_token'):
            raise RuntimeError('Sign in to Antigravity again to refresh its session')
        client, secret = oauth_client(binary)
        renewed = api.request('https://oauth2.googleapis.com/token', dict(
            grant_type='refresh_token', client_id=client, client_secret=secret, refresh_token=token['refresh_token']), form=True)
        access = renewed.get('access_token')
        if not access:
            raise RuntimeError('Antigravity session refresh failed; sign in again')
    headers = {'Authorization': f'Bearer {access}', 'User-Agent': 'antigravity/hub/2.9.1 darwin/arm64'}
    setup = api.request('https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist',
                        dict(metadata=dict(ideType='ANTIGRAVITY', platform='PLATFORM_UNSPECIFIED', pluginType='GEMINI')), headers)
    project = setup.get('cloudaicompanionProject')
    if not project:
        # Non-onboarded identities can return placeholder 100%-remaining summaries.
        raise RuntimeError('Antigravity account needs sign-in/onboarding; no verified quota project')
    if isinstance(project, dict):
        project = project.get('id')
    if not project:
        raise RuntimeError('Antigravity quota project is unavailable')
    payload = api.request('https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary', dict(project=project), headers)
    plan = (setup.get('paidTier') or setup.get('currentTier') or {}).get('name')
    return dict(name='Antigravity', windows=antigravity_rows(payload), plan=plan, observed_at=time.time(), error=None)
