# Herdr AI Usage

AI subscription usage and reset timers for the **Herdr native desktop app**.

A sidebar panel for Codex, Claude, Gemini chat, and Antigravity usage, with percentage
bars, reset countdowns, exact local reset times, and a refresh button. Works with
the Herdr desktop app, independently of Herdr TUI.

## Install

Tested with Herdr native app 0.1.11 on macOS Apple Silicon.

Requirements: a running Herdr native app and Apple's Python 3.9+ at
`/usr/bin/python3`, provided by Xcode or Xcode Command Line Tools. No Homebrew
Python, pip packages, Node.js, or npm packages are needed to run the mod.

Sign in to the providers you want to display. Codex and Claude use their
installed CLIs; Antigravity uses its existing app sign-in. Gemini chat needs
access to a signed-in Chrome session.

Apple's developer-tools Python is not guaranteed on a clean macOS installation.
If `/usr/bin/python3 --version` asks for developer tools, install Apple's
[Command Line Tools](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools).
The installer deliberately configures `/usr/bin/python3` rather than a Python
found on `PATH`.

Download and extract a release ZIP, or clone:

```sh
git clone https://github.com/jmalicki/herdr-mod-ai-usage.git
cd herdr-mod-ai-usage
```

Then install from that directory:

```sh
/usr/bin/python3 install.py
```

This duplicates the `main` layout as `usage`, adds a sidebar panel, and switches
to it. Shipped layouts and mods stay untouched. Previous personal files are
backed up under `backups/`. Running the installer again updates this mod.
The installed helper is self-contained in `~/.config/herdr-app/mods/plan-usage/`.
Use `--base NAME --layout NAME` to choose another sidebar layout.

To return to the standard interface:

```sh
herdr-app do layout.switch '{"name":"main"}'
```

Switching layouts stops this layout's panel and polling. To fully remove it,
switch to another layout, then delete only `layouts/usage.json`,
`mods/plan-usage/`, and `data/plan-usage/` from `~/.config/herdr-app/`.

## Data and behavior

### Display settings

Click **Settings** beside **Plan usage** to show or hide each provider and its
individual limits. Gemini chat, Antigravity, and the Fable model limit start hidden.
Enable the displays you want in this dialog. Hidden providers stop refreshing; their last cached limits remain
available in the settings list so they can be restored.

You can also toggle progress bars, reset countdowns, exact reset times, and
last-updated labels. The countdown and reset date share a line when there is
room and wrap onto two lines automatically in a narrower sidebar.
Changes take effect immediately and persist across restarts in Herdr's shared
state under `plan-usage.preferences`. Reinstalling preserves your selections.
The panel measures its visible content and returns unused height to Spaces and
Agents. At 310 logical pixels it stops growing and scrolls its own contents.
Drag the divider immediately above Plan usage to set its height manually.
That disables automatic fitting and retains your chosen size. Re-enable
**Fit panel to content** in the panel's Settings to restore automatic sizing.

Gemini chat and Antigravity are separate allowances. Legacy Gemini CLI is not
included. Antigravity uses Google's OAuth and `retrieveUserQuotaSummary` APIs
with the existing `~/.gemini/jetski-standalone-oauth-token` sign-in. Expired
access tokens are refreshed in memory using the matching public OAuth client
constants in the installed Antigravity binary. No tokens are printed, stored
in quota caches, or written back to Antigravity. The app does not need to stay
open. The current OAuth constant resolver supports Apple Silicon app binaries.

Gemini chat uses the cookie-authenticated persisted GraphQL query behind
`https://gemini.google.com/usage`. It reads Google session cookies from Chrome's
`Default` profile and decrypts them in memory with Chrome Safe Storage in macOS
Keychain, using Apple's CommonCrypto system library through Python's standard-library `ctypes`. It does not read chat history.
These are internal Google interfaces, so changes upstream may require updates.

### Connecting Gemini chat

macOS can deny access to Chrome's Cookies database. If the panel reports
that session access is blocked, Gemini chat cannot authenticate until that
access is available. This is an OS privacy restriction, not an API parsing
failure. Gemini chat is optional and disabled by default.

To use automatic session discovery, sign in at `https://gemini.google.com/usage`
in Chrome, grant the application running the helper (Herdr, or Terminal when
running the collector yourself) access under **System Settings → Privacy &
Security → Full Disk Access**, then relaunch that application and refresh.
If macOS asks for Chrome Safe Storage Keychain access, that is used only to
decrypt the matching Google cookies. Do not change permissions on Chrome's
database or disable macOS privacy protections globally.

Alternatively, a protected local file can supply a Cookie header explicitly:
set `HERDR_USAGE_GEMINI_COOKIE_FILE` to its absolute path in the environment
starting Herdr. The file must have mode `600`; cookies are read into memory
and sent only to `gemini.google.com`, with redirects disabled. Treat this
file as a credential, keep it outside this project, and never paste its
contents into chat or commit it. Session expiry requires updating it.

`HERDR_USAGE_CHROME_PROFILE='Profile 1'` selects a different Chrome profile.
The reader uses only the selected profile and does not silently select another
Google account. The quota belongs to that profile's default signed-in Google
account, which may differ from the account signed into the native Gemini app.

The Codex/Claude helper asks Codex's `account/rateLimits/read` and Claude Code's streaming
`get_usage` control request. It sends no model prompts, starts no turns, reads no
credential files, and does not modify your agent settings. Short-lived helpers
use the CLIs' existing authentication and network connections. Claude helpers
run in safe mode without hooks, customizations, MCP servers, or persisted sessions.
The Claude control request is an internal interface and may change with CLI updates.

The panel shows **account allowance percentages**, rather than a token balance
or per-agent context meter. It displays only returned windows, including model
specific limits; some accounts return a weekly window without a five-hour one.
Quota resets belong to the provider and are not necessarily midnight.

Each provider is queried every five minutes. The panel checks its cache and
updates countdowns every minute. Refresh requests have a 30-second cooldown.
The helper requests all providers concurrently, with bounded request timeouts,
then terminates its own helper processes. It never terminates running agents.
Failures preserve the last successful observation with an offline/stale label.
After a cached window expires, its percentage is hidden until a new reading
arrives; the panel never guesses that usage became zero.

State is quota-only JSON under `~/.config/herdr-app/data/plan-usage/` with private
file permissions. `CODEX_HOME` and `CLAUDE_CONFIG_DIR` are honored by the CLIs.
`HERDR_USAGE_CODEX_BIN` and `HERDR_USAGE_CLAUDE_BIN` override executable discovery.
This panel reads accounts on the local computer; SSH agents' separate accounts
are not included.

## Verify

```sh
/usr/bin/python3 -m unittest discover -s tests -v
node --test tests/preferences.test.mjs
/usr/bin/python3 build_release.py
/usr/bin/python3 collector.py --force
herdr-app check ~/.config/herdr-app/mods/plan-usage
herdr-app status
```

Protocol references:

- [Codex app-server](https://learn.chatgpt.com/docs/app-server)
- [Claude status-line quota fields](https://code.claude.com/docs/en/statusline)
- [Claude get_usage interoperability reference](https://github.com/VHemanth45/herdr_agents_tracker/blob/main/usage_tracker/providers/claude.py)
- [Herdr native guide](https://herdr.dev/guide/)
- [Gemini chat API interoperability notes](https://github.com/steipete/CodexBar/blob/main/docs/gemini.md)
- [Antigravity API interoperability notes](https://github.com/steipete/CodexBar/blob/main/docs/antigravity.md)


## Architecture and releases

This is source code loaded by Herdr, not a Swift application. The interface
uses JavaScript and Herdr's native GPUI components. Python helpers collect
quotas and install the mod. There is no compilation or signing step.

CI runs the tests on macOS and Linux with Python 3.9, 3.13 and 3.15, plus
Node.js 24 for the JavaScript development tests. A separate macOS job tests
Apple's `/usr/bin/python3` directly without installing another Python.

Native integration jobs download checksum-verified Herdr GUI/core 0.1.11 on
macOS ARM64, Linux x64 and Linux ARM64. They install the release ZIP into an
isolated profile, run the actual helper against synthetic cached quotas, and
exercise native rendering, narrow/wide sidebars, manual panel resizing,
automatic fitting and the settings dialog. Linux uses a virtual X11 desktop
and Mesa software Vulkan; macOS uses its native window and Apple Python.
Screenshots, status and observations are retained as CI artifacts. A test-only
subclass observes the shipped view; it is excluded from release archives.
These tests need no provider accounts and do not test live authentication,
provider API availability, mouse dragging or Windows GUI behavior.

Pushing a `v*` tag matching `VERSION` runs the tests and creates a GitHub
release containing an installable source ZIP and SHA-256 checksum. Nothing
is published by running the installer or building an archive locally.
See [CONTRIBUTING.md](CONTRIBUTING.md) for development and release steps.

## License and acknowledgments

MIT. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
This is an independent community mod for Herdr.
