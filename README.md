# Phone Workflows

N.E.K.O phone and WeChat workflows synchronized from the canonical
`hermes-phone-agent` implementation. The plugin does not expose raw tap,
swipe, type, shell, or APK tools to the model.

## Model tools

- `phone_status`: read-only Android, Helper, permission, OCR, and foreground status.
- `wechat_read`: bounded text and image context from a verified conversation.
- `wechat_prepare_reply`: verify the destination and produce an exact preview.
- `wechat_send_confirmed`: consume a one-time token and send exactly that preview.

`delivery_uncertain` is terminal. The plugin never automatically repeats that
message.

## Setup

The host must provide Android SDK Platform Tools (`adb`) and one authorized
Android device or emulator. Set `android_serial` when more than one device is
connected. The default `adb` backend is self-contained. Hybrid Appium support
is optional and gracefully falls back to ADB unless both the Appium server and
Python client are installed.

```toml
[phone_workflows]
backend = "adb"
android_serial = "emulator-5554"
ocr_helper_path = ""
confirmation_ttl_seconds = 300
```

The bundled Helper APK is installed only through the confirmation-gated
`setup_action` entry. Notification Listener and Accessibility are separate
actions and permissions; installing the APK does not enable either one.

On macOS, startup compiles the synchronized Vision OCR source into the
plugin's private data directory when `swiftc` is available. Set
`ocr_helper_path` to use an explicitly managed binary instead.

## Upstream synchronization

`hermes-phone-agent` is the only implementation source. Files below
`upstream/phone_core/` and the APK below `assets/android/` are generated and
must not be edited manually.

```bash
python3 scripts/sync_from_hermes.py --source /path/to/hermes-phone-agent
python3 scripts/sync_from_hermes.py --source /path/to/hermes-phone-agent --check
```

`UPSTREAM.json` records the exact Git commit, Helper version, APK checksum,
and every synchronized file hash.

## Development

From the N.E.K.O repository root:

```bash
uv run pytest plugin/plugins/phone_workflows/tests -q
uv run --with pip neko-plugin sync phone_workflows --clean
uv run neko-plugin check phone_workflows
uv run neko-plugin check -r phone_workflows
```

The Market repository name is `n.e.k.o_plugin_phone_workflows`. This plugin
contains AGPL-3.0-only code synchronized from `hermes-phone-agent` and is
distributed under the same license; provenance and hashes are retained in
`UPSTREAM.json`.
