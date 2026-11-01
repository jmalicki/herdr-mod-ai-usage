# Contributing

The interface is a JavaScript mod for Herdr's native GPUI runtime. The collectors
and installer use Python's standard library. Node.js is needed only for JavaScript development tests, not to run the mod.
The runtime target is Apple's Python 3.9 at `/usr/bin/python3`; Gemini cookie
decryption uses the macOS CommonCrypto system library. There is no compilation step.

Run the tests without provider accounts:

```sh
/usr/bin/python3 -m unittest discover -s tests -v
node --test tests/preferences.test.mjs
/usr/bin/python3 build_release.py
```

For interface changes, run `herdr-app check mods/plan-usage`, install into the
running app with `/usr/bin/python3 install.py`, and check the result there. CI verifies
parsing, settings behavior, process cleanup and release packaging; it does not
run the Herdr GUI or query signed-in provider accounts.

Keep authentication values, personal screenshots, machine-specific files,
and backups out of commits. Provider parsers must distinguish missing quota
data from reported zero usage, and expired readings must not imply a reset.

## Releasing

1. Update `VERSION` to the release version and commit the changes.
2. Push a matching tag, for example `v0.1.0`.
3. GitHub Actions runs the test matrix and publishes a ZIP plus `SHA256SUMS`.

The release package uses an explicit file list. It excludes local configuration,
credentials, backups, screenshots, generated declarations, and development tools.
Release asset names follow the GitHub repository name, so naming the repository
does not require renaming the internal `plan-usage` mod.
