# Hermes Phone Agent / Phone MCP Server source audit

Date: 2026-09-21

## Scope and method

This audit compares the checked-out primary sources, not only their READMEs:

- `hermes-phone-agent` checkout: `hermes-phone-agent`, commit `73735f57c50aa300ed6b69272500bd469de9a146`.
- `phone-mcp-server` checkout: `phone-mcp-server`, commit `f48a4476939ac00b0687cf0dc57797ad3beeaffe` (`v0.2.1`).

The repositories are related snapshots, but they are not feature-equivalent today. The MCP repository's history says it synchronized reusable phone automation and briefly copied in the Android helper, then deliberately removed that copy in favor of the canonical Phone Agent release. Its remaining Python package is an older standalone projection of the control side. The current Hermes repository has since added substantial event security, conversation isolation, friend-request handling, image inspection, and WeChat reliability work.

## Bottom line for N.E.K.O

`phone-mcp-server` is a useful transport/backend seed, not the complete product to vendor unchanged. A credible N.E.K.O integration needs all three layers below in one installable plugin product:

1. **Device runtime:** a pinned canonical `hermes-phone-agent` APK, checksum, explicit install/upgrade UI, and separately gated Notification Listener and Accessibility grants.
2. **Private low-level driver:** the updated ADB/Appium/OCR and WeChat implementation, reachable by the plugin but normally hidden from the model.
3. **N.E.K.O domain workflows:** small high-level entries such as status, WeChat read/context, draft/confirm/send, and later event enrollment. The workflow layer must own confirmation, idempotency, delivery uncertainty, screenshots as image parts, operation serialization, and recovery.

Merely registering the current 18 MCP tools would omit the most important host-side behavior and make the model responsible for fragile sequences. Conversely, exposing all Hermes event automation by default would silently enlarge the trust boundary. Install once, but enable capabilities progressively.

## 1. What Hermes Phone Agent actually contains

The canonical project has three separately meaningful components, as its own component table states: `phone_use`, `phone_events`, and the Android helper APK ([README.md](hermes-phone-agent/README.md:5)).

### 1.1 `phone_use`: one consolidated Hermes tool

Hermes exposes one `phone_use` model tool, not 18 independent tools. Its action discriminator includes capture; tap/double-tap/long-press/swipe; type/clear/set text; key events; launch/stop/list/current app; APK install; shell; wait/device info; three WeChat composites; and begin/end workflow ([schema.py](hermes-phone-agent/plugins/phone_use/schema.py:26)). The plugin registers that one tool plus session-end cleanup and a pre-tool-call guard ([__init__.py](hermes-phone-agent/plugins/phone_use/__init__.py:17)).

This wrapper adds behavior absent from a raw backend:

- Every mutating action produces a follow-up hierarchy capture, including failures, while screenshots become native multimodal results rather than JSON base64 ([tool.py](hermes-phone-agent/plugins/phone_use/tool.py:833), [tool.py](hermes-phone-agent/plugins/phone_use/tool.py:882)).
- Physical operations are FIFO-serialized across tasks and sessions ([tool.py](hermes-phone-agent/plugins/phone_use/tool.py:89), [tool.py](hermes-phone-agent/plugins/phone_use/tool.py:481)).
- A five-minute workflow approval is bound to `task_id`, `session_id`, goal, and an allowed-action set; `shell`, `install_apk`, and `wechat_reply` cannot inherit it ([tool.py](hermes-phone-agent/plugins/phone_use/tool.py:57), [tool.py](hermes-phone-agent/plugins/phone_use/tool.py:70), [schema.py](hermes-phone-agent/plugins/phone_use/schema.py:65)).
- Foreground-package lookup is authoritative for generic interactions. Unknown foreground state fails closed instead of accepting a model-supplied package ([tool.py](hermes-phone-agent/plugins/phone_use/tool.py:445)).
- An authenticated automatic phone turn is restricted to `phone_use`, `web_search`, and `web_extract` ([__init__.py](hermes-phone-agent/plugins/phone_use/__init__.py:17)).

### 1.2 `phone_events`: a Hermes gateway platform

This is not present in the MCP repository. It combines two event sources:

- Tier 1 parses selected `adb logcat` notifications/crashes and normalizes them into `PhoneEvent` objects ([logcat_monitor.py](hermes-phone-agent/plugins/phone_events/logcat_monitor.py:1), [logcat_monitor.py](hermes-phone-agent/plugins/phone_events/logcat_monitor.py:40)).
- Tier 2 receives structured notification/UI events from the APK through an ADB-forwarded loopback socket ([socket_listener.py](hermes-phone-agent/plugins/phone_events/socket_listener.py:1)).

Before dispatch, events are package-filtered, rate-limited, and deduplicated ([event_filter.py](hermes-phone-agent/plugins/phone_events/event_filter.py:42)); sensitive patterns are redacted and bodies truncated ([redact.py](hermes-phone-agent/plugins/phone_events/redact.py:13), [redact.py](hermes-phone-agent/plugins/phone_events/redact.py:39)). Phone text is explicitly wrapped as untrusted data, and only a host policy decision can add `TASK_SOURCE` ([adapter.py](hermes-phone-agent/plugins/phone_events/adapter.py:1), [adapter.py](hermes-phone-agent/plugins/phone_events/adapter.py:32)).

The adapter also creates isolated lanes for WeChat conversations instead of mixing phone events into one context ([adapter.py](hermes-phone-agent/plugins/phone_events/adapter.py:200)). It delivers reports and approvals through a configured Telegram destination, and the platform remains opt-in until such a destination exists ([__init__.py](hermes-phone-agent/plugins/phone_events/__init__.py:17), [__init__.py](hermes-phone-agent/plugins/phone_events/__init__.py:46)). These Hermes-specific routing semantics need a N.E.K.O-native replacement, not blind copying.

## 2. Android helper: capabilities, permissions, and authentication

The current helper is package `com.hermes.phoneagent`, Android min SDK 26, target/compile SDK 34, version `0.2.4`; it deliberately has no third-party Android dependencies ([build.gradle.kts](hermes-phone-agent/helper-apk/app/build.gradle.kts:6)). The canonical release APK in this checkout has SHA-256 `6223522d3e060784ae57184cc2ef6eead4c452cad3b32f251390f177bdbca68f`.

### Capabilities

- `PhoneNotificationListener` extracts only package, app label, title, body, timestamp, notification key, and WeChat conversation metadata; it does not extract actions or `PendingIntent`s ([PhoneNotificationListener.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/PhoneNotificationListener.kt:11), [PhoneNotificationListener.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/PhoneNotificationListener.kt:37)). For WeChat it normalizes volatile message-count suffixes and records group/private/unknown plus a conversation hash ([PhoneNotificationListener.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/PhoneNotificationListener.kt:42), [PhoneNotificationListener.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/PhoneNotificationListener.kt:77)). It replays active friend-request notifications after reconnect ([PhoneNotificationListener.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/PhoneNotificationListener.kt:138)).
- `PhoneAccessibilityService` observes window-state changes and only dialog/toast/popup-like content changes. Its configuration explicitly sets `canRetrieveWindowContent=false`; it emits metadata and a bounded content description, not the view hierarchy or field contents ([PhoneAccessibilityService.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/PhoneAccessibilityService.kt:8), [accessibility_config.xml](hermes-phone-agent/helper-apk/app/src/main/res/xml/accessibility_config.xml:9)).
- `EventSocketService` has two jobs: emit authenticated events and set clipboard text from bounded base64, enabling Unicode and shell-sensitive input before ADB paste ([EventSocketService.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/EventSocketService.kt:46), [EventSocketService.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/EventSocketService.kt:64)). The ADB backend invokes exactly that clipboard action for any text outside `[A-Za-z0-9._-]+`, then sends paste keycode 279 ([adb_backend.py](phone-mcp-server/phone_control/adb_backend.py:413)). Thus the helper is not only an event add-on; normal Chinese WeChat input on the ADB backend depends on it.
- `BootReceiver` does not auto-start monitoring; it only records boot completion, leaving service start to a host session ([BootReceiver.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/BootReceiver.kt:8)).

### Permissions and trust boundary

The manifest requests boot completion, Internet, network-state, foreground-service, and connected-device foreground-service permissions. It explicitly does not request contacts, SMS, call log, camera, microphone, or location ([AndroidManifest.xml](hermes-phone-agent/helper-apk/app/src/main/AndroidManifest.xml:4), [AndroidManifest.xml](hermes-phone-agent/helper-apk/app/src/main/AndroidManifest.xml:13)).

Notification Listener and Accessibility are separately declared system-bound services and require explicit grant ([AndroidManifest.xml](hermes-phone-agent/helper-apk/app/src/main/AndroidManifest.xml:25), [AndroidManifest.xml](hermes-phone-agent/helper-apk/app/src/main/AndroidManifest.xml:37)). The event/clipboard service is exported but protected by signature-level `WRITE_SECURE_SETTINGS`, so an ordinary app cannot start it; ADB shell can ([AndroidManifest.xml](hermes-phone-agent/helper-apk/app/src/main/AndroidManifest.xml:70)).

The socket binds only `127.0.0.1`. Host and helper exchange fresh nonces and mutually prove knowledge of a per-session token with HMAC-SHA256; unauthenticated clients time out and receive no events ([EventSocketService.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/EventSocketService.kt:22), [EventSocketService.kt](hermes-phone-agent/helper-apk/app/src/main/java/com/hermes/phoneagent/EventSocketService.kt:144)). The host generates the token, starts the protected service, creates `adb forward`, and verifies both sides of the handshake ([socket_listener.py](hermes-phone-agent/plugins/phone_events/socket_listener.py:71), [socket_listener.py](hermes-phone-agent/plugins/phone_events/socket_listener.py:141), [socket_listener.py](hermes-phone-agent/plugins/phone_events/socket_listener.py:197)). Current code recreates the forward and restarts the service after emulator/helper failure ([socket_listener.py](hermes-phone-agent/plugins/phone_events/socket_listener.py:156)).

### Consequence for N.E.K.O

APK installation and three permissions must not be collapsed into one silent setup action:

- **Base input capability:** install the pinned APK; this permits the protected clipboard service when started by ADB, without granting notification or accessibility access.
- **Event capability:** separately explain and grant Notification Listener.
- **UI metadata capability:** separately explain and grant Accessibility. It is lower-data than a normal accessibility scraper, but still a sensitive Android grant.

The current Hermes `setup.sh` installs the APK, grants both listener services, and compiles OCR in one run ([setup.sh](hermes-phone-agent/setup.sh:65), [setup.sh](hermes-phone-agent/setup.sh:80), [setup.sh](hermes-phone-agent/setup.sh:88), [setup.sh](hermes-phone-agent/setup.sh:109)). N.E.K.O should split those operations into explicit UI states.

## 3. What `phone-mcp-server` exposes

The MCP server exposes 18 individual tools: 15 generic operations plus `phone_wechat_open_chat`, `phone_wechat_reply`, and `phone_wechat_collect_context` ([mcp_server.py](phone-mcp-server/mcp_server.py:197), [mcp_server.py](phone-mcp-server/mcp_server.py:379)). It also defines `phone://policy` and `phone://status` resources ([mcp_server.py](phone-mcp-server/mcp_server.py:426)). It can run stdio or SSE ([mcp_server.py](phone-mcp-server/mcp_server.py:460)).

The parallel HTTP server offers health/status, `POST /phone/{action}`, OpenAI tool schemas, and OpenAI function dispatch ([http_server.py](phone-mcp-server/http_server.py:486), [http_server.py](phone-mcp-server/http_server.py:554)). Its 18 schemas mirror the MCP surface ([http_server.py](phone-mcp-server/http_server.py:348)). HTTP blocks `install_apk` and `shell` at the transport dispatcher ([http_server.py](phone-mcp-server/http_server.py:230), [http_server.py](phone-mcp-server/http_server.py:488)); those two are not MCP tools at all.

The low-level backends remain useful:

- Pure ADB performs device discovery, screenshots, hardened XML hierarchy parsing, coordinates/touch, text, key events, app management, install, and sanitized shell ([adb_backend.py](phone-mcp-server/phone_control/adb_backend.py:81), [adb_backend.py](phone-mcp-server/phone_control/adb_backend.py:186), [adb_backend.py](phone-mcp-server/phone_control/adb_backend.py:343)).
- Hybrid mode delegates normal operations to ADB and lazily uses Appium for Unicode/input or hierarchy fallback ([appium_backend.py](phone-mcp-server/phone_control/appium_backend.py:151), [appium_backend.py](phone-mcp-server/phone_control/appium_backend.py:242)). The manager may install the UiAutomator2 Appium driver and starts Appium on loopback with `--relaxed-security` ([appium_manager.py](phone-mcp-server/phone_control/appium_manager.py:79)). This process-management capability should remain private to the plugin and clearly disclosed.
- macOS Vision OCR consumes ADB screenshots, not the Mac display, and turns recognized text into clickable elements ([host_ocr.py](phone-mcp-server/phone_control/host_ocr.py:1), [host_ocr.py](phone-mcp-server/phone_control/host_ocr.py:86)).

## 4. Policy and approval are not equivalent

Both projects retain the same basic policy engine: hot-reloaded YAML, default `report`, app profiles, prioritized event rules, per-app allow/block actions, and global restrictions ([policy.py](phone-mcp-server/phone_control/policy.py:127), [policy.py](phone-mcp-server/phone_control/policy.py:185), [policy.py](phone-mcp-server/phone_control/policy.py:346)).

But execution differs materially:

- Hermes has real CLI/gateway approval callbacks, session/permanent grants for ordinary actions, forced one-time approval for `wechat_reply`, `shell`, and APK installation, workflow scopes, and auto-event authorization ([tool.py](hermes-phone-agent/plugins/phone_use/tool.py:406), [tool.py](hermes-phone-agent/plugins/phone_use/tool.py:505)). Exact WeChat destination and message text are shown in the approval summary ([tool.py](hermes-phone-agent/plugins/phone_use/tool.py:633)).
- Standalone MCP has no approval channel. `_policy_check` simply blocks any action named in `global_restrict` ([mcp_server.py](phone-mcp-server/mcp_server.py:166)). Its default policy globally restricts only `install_apk` and `shell`, neither of which is exposed by MCP, so ordinary taps/typing and WeChat replies execute immediately once per-app policy permits them ([phone-policy.yaml](phone-mcp-server/phone-policy.yaml:80)).

Therefore `phone_wechat_reply` is not safe to expose directly as N.E.K.O's user-facing send contract. N.E.K.O needs its own preview/confirmation object bound to device, conversation, exact text, session, expiry, and a one-time nonce. The raw MCP tool must only be callable after that gate.

## 5. WeChat behavior: retained baseline versus current canonical code

### Baseline retained by MCP

The MCP snapshot has deterministic title normalization, fuzzy matching, search when a row is absent, post-open header/input verification, bounded context scopes, overlap-aware scrolling, and conservative delivery confirmation ([wechat.py](phone-mcp-server/phone_control/wechat.py:438), [wechat.py](phone-mcp-server/phone_control/wechat.py:591), [wechat_context.py](phone-mcp-server/phone_control/wechat_context.py:26), [wechat_context.py](phone-mcp-server/phone_control/wechat_context.py:105)). It does not retry after a send attempt that cannot be confirmed ([wechat.py](phone-mcp-server/phone_control/wechat.py:628)).

### Canonical functionality added or improved afterward

The current Hermes implementation contains all of the following missing from the MCP snapshot:

- More robust launch/list/search recovery, waits for transitions, Contacts-tab escape, stale-search clearing, unique symbol-only chat handling, and a recently verified symbol-title hint ([wechat.py](hermes-phone-agent/plugins/phone_use/wechat.py:674), [wechat.py](hermes-phone-agent/plugins/phone_use/wechat.py:766)).
- Voice/text composer switching, settling after paste, and a narrowly bounded second tap when Send remains visibly present. Once any send attempt produces uncertain state, the outer workflow still refuses a whole-message retry ([wechat.py](hermes-phone-agent/plugins/phone_use/wechat.py:840), [wechat.py](hermes-phone-agent/plugins/phone_use/wechat.py:883), [wechat.py](hermes-phone-agent/plugins/phone_use/wechat.py:944)).
- A deterministic named friend-request acceptance workflow that verifies the requester, does not set a remark, verifies acceptance, and always returns Home ([wechat.py](hermes-phone-agent/plugins/phone_use/wechat.py:1001)). Friend notification approval bypasses the model and waits through Hermes' Telegram approval channel without holding the phone queue ([adapter.py](hermes-phone-agent/plugins/phone_events/adapter.py:119), [adapter.py](hermes-phone-agent/plugins/phone_events/adapter.py:608)).
- Context collection now excludes keyboard OCR, can identify/open only plausible image bubbles, verifies the image viewer activity, returns to chat, searches past a text limit for the first image, and includes image/position markers in repeated-page detection ([wechat_context.py](hermes-phone-agent/plugins/phone_use/wechat_context.py:26), [wechat_context.py](hermes-phone-agent/plugins/phone_use/wechat_context.py:192), [wechat_context.py](hermes-phone-agent/plugins/phone_use/wechat_context.py:271)). Screenshots are emitted as model image parts ([tool.py](hermes-phone-agent/plugins/phone_use/tool.py:774)).
- WeChat notifications carry stable conversation metadata; group automation requires an explicit `@Void_DRSAI` policy match, other group notifications are ignored, and private conversations can be task sources ([phone-policy.yaml](hermes-phone-agent/phone-policy.yaml:174), [phone-policy.yaml](hermes-phone-agent/phone-policy.yaml:199), [phone-policy.yaml](hermes-phone-agent/phone-policy.yaml:209)).

N.E.K.O should port/sync these current routines before treating WeChat as supported. Building a high-level workflow over the old MCP snapshot preserves known bugs.

## 6. Exact retained / omitted / changed inventory

| Area | `phone-mcp-server` state relative to current Hermes | Evidence / impact |
|---|---|---|
| Data model/backend ABC | Retained byte-for-byte at the audited commits | `/phone_control/backend.py` matches `/plugins/phone_use/backend.py`; useful shared contract. |
| Sanitizers | Retained byte-for-byte | `/phone_control/sanitize.py` matches canonical; validates text, coordinates, packages, APK paths, keys, and shell. |
| Appium manager | Retained byte-for-byte | `/phone_control/appium_manager.py` matches canonical. |
| ADB backend | Forked older copy | Canonical adds `image_hierarchy` and merges real ImageView hierarchy with Vision candidates ([adb_backend.py](hermes-phone-agent/plugins/phone_use/adb_backend.py:188)). |
| Hybrid backend | Logic retained; imports repackaged | Standalone imports `phone_control.*`; plugin uses relative imports. |
| OCR | Forked older copy and different install path | MCP supports `PHONE_OCR_HELPER` and defaults to `~/.phone-mcp/bin`; canonical defaults to `~/.hermes/bin` and adds visual image candidates ([host_ocr.py](hermes-phone-agent/plugins/phone_use/host_ocr.py:85)). |
| WeChat open/reply | Older snapshot | Missing current navigation, composer, dropped-tap, symbol-title, friend-request, and recovery work. |
| WeChat context | Older snapshot | Missing keyboard filtering, image opening/verification, improved paging, and native multimodal shaping. |
| Policy parser | Mostly retained, but older | MCP lacks `conversation_type` matching added to canonical policy ([policy.py](hermes-phone-agent/plugins/phone_use/policy.py:62), [policy.py](hermes-phone-agent/plugins/phone_use/policy.py:151)). |
| Hermes schema/tool wrapper | Omitted | No consolidated tool, follow-up captures, workflow approval, session cleanup, FIFO queue, event-bound policy, idempotent auto replies, or N.E.K.O-equivalent hooks. |
| Phone events platform | Entirely omitted | No logcat monitor, authenticated socket client, filter/redaction, routing, task-source boundary, or conversation lanes. |
| Android helper source/APK | Deliberately omitted from final MCP commit | MCP README downloads canonical `v0.2.1` ([README.md](phone-mcp-server/README.md:63)); current canonical APK is `v0.2.4`. |
| Transport | Changed/added | MCP splits the consolidated action API into 18 FastMCP tools, adds stdio/SSE plus HTTP/OpenAI schemas and two resources. |
| Screenshots | Regressed for agent integration | MCP serializes `image_base64` in JSON ([mcp_server.py](phone-mcp-server/mcp_server.py:137)); canonical returns native image parts. |
| Configuration | Changed | Standalone is environment driven; Hermes resolves serial from `config.yaml` before legacy environment fallback ([tool.py](hermes-phone-agent/plugins/phone_use/tool.py:136)). N.E.K.O should use plugin config, not new public env-only UX. |

## 7. Packaging and runtime findings

`phone-mcp-server` declares Python 3.10+, `mcp`, Starlette, Uvicorn, PyYAML, and defusedxml; Appium's Python client is optional ([pyproject.toml](phone-mcp-server/pyproject.toml:5)). Runtime also needs `adb`; hybrid mode needs the Node Appium binary and may install its UiAutomator2 driver; OCR needs macOS 13+/Xcode CLI and a compiled Swift helper ([README.md](phone-mcp-server/README.md:39), [README.md](phone-mcp-server/README.md:49)).

There is a real packaging defect: scripts point to top-level `mcp_server:mcp.run` and `http_server:main` ([pyproject.toml](phone-mcp-server/pyproject.toml:25)), but a locally built wheel contained only `phone_control/**` and dist-info, not `mcp_server.py` or `http_server.py`. Consequently `pip install .` produces broken console entry points unless run from a source checkout that happens to put those modules on `sys.path`. N.E.K.O must not vendor this wheel layout unchanged. Move launchers under the package or explicitly package `py_modules`, and provide a real `main()` for MCP rather than pointing the console script at `FastMCP.run` without transport configuration.

The helper is also version-skewed: MCP documentation pins `v0.2.1` ([README.md](phone-mcp-server/README.md:63)); current canonical source and releases are `v0.2.4` ([build.gradle.kts](hermes-phone-agent/helper-apk/app/build.gradle.kts:14)). The plugin should vendor one audited APK from the canonical repository and verify its checksum before offering installation.

## 8. Test evidence and residual gaps

At audit time:

- `python3 -m pytest -q tests/test_phone_plugins.py` in `virtual-phone`: **139 passed** in 13.28 s. The file exercises 134 named test functions plus parametrization. It covers helper clipboard input, OCR/image candidates, follow-up capture contracts, policy/approval isolation, workflow expiry, FIFO serialization, extensive WeChat navigation/reply/context/image/friend paths, event lanes, task-source authenticity, helper authentication/recovery, redaction, and fail-closed behavior ([test_phone_plugins.py](hermes-phone-agent/tests/test_phone_plugins.py:36), [test_phone_plugins.py](hermes-phone-agent/tests/test_phone_plugins.py:765), [test_phone_plugins.py](hermes-phone-agent/tests/test_phone_plugins.py:1379), [test_phone_plugins.py](hermes-phone-agent/tests/test_phone_plugins.py:2614), [test_phone_plugins.py](hermes-phone-agent/tests/test_phone_plugins.py:4118)).
- `python3 -m pytest -q tests/test_phone_control_features.py` in `phone-mcp-server`: **5 passed** in 0.40 s. Those five tests cover title normalization, collection scope, page merging, JSON serialization, and blocking globally restricted actions ([test_phone_control_features.py](phone-mcp-server/tests/test_phone_control_features.py:11)). There are no MCP initialization/tool-discovery tests, HTTP route tests, wheel/entry-point tests, Android-helper compatibility tests, real ADB tests, or current WeChat reliability tests.

Both suites are predominantly local unit tests. Before release, N.E.K.O needs an end-to-end matrix using a temporary plugin config and real MCP subprocess imports, plus opt-in emulator tests for helper version/status, Unicode clipboard, screenshot image parts, chat verification, confirmed send, uncertain delivery with no resend, and event authentication/reconnect.

## 9. Recommended N.E.K.O adaptation boundary

### Ship as one user-facing repository/plugin

The independent N.E.K.O repository should own:

- plugin manifest/runtime and UI;
- a pinned, corrected Python phone runtime synchronized from current canonical source;
- the canonical `v0.2.4` APK and checksum/license/source notice;
- a private MCP launcher only if the existing N.E.K.O MCP adapter remains the desired process boundary;
- N.E.K.O-native confirmation and workflow state;
- setup/status diagnostics and migrations.

The user should not separately clone `phone-mcp-server`, but provenance should remain explicit and upstream fixes should be syncable.

### Model-visible surface

Expose only high-level capabilities initially:

- `phone_status`: selected device, connection, helper version, base clipboard readiness, event grants, OCR/Appium status.
- `wechat_read`: verified conversation open plus bounded text/images; return actual image parts.
- `wechat_prepare_reply`: resolve and verify destination, normalize exact draft, and create a short-lived confirmation object.
- `wechat_send_confirmed`: consume that object once, serialize device access, run the current canonical reply routine, and report `confirmed`, `not_attempted`, or `delivery_uncertain`.

Do not expose raw MCP tools to the model by default. Keep a separately enabled expert/debug surface for capture/tap/swipe only. Never expose shell or APK install to the model.

### Event support should be phase two and opt-in

Port the authenticated socket client and event normalization into N.E.K.O rather than expecting the MCP server to provide events; current MCP has no event API. Map events to N.E.K.O-owned isolated conversation identities, preserve the untrusted-data/task-source distinction, redact before model exposure, and let policy decide report/ignore/task. Automatic reply should not be the default. Friend-request approval should remain deterministic and bypass the model if implemented.

### Source of truth

For control and WeChat logic, sync from current `hermes-phone-agent/plugins/phone_use`, not the older MCP copy. For helper behavior, source only from `hermes-phone-agent/helper-apk`. The MCP repository should contribute transport ideas and standalone packaging after its entry points are repaired, not define feature parity.

## Final assessment

The Android helper is a meaningful part of both input and event functionality, while `phone-mcp-server` currently contains only the older control half and delegates the helper to an outdated external release. The missing Hermes host layer is precisely where approvals, event authenticity, conversation isolation, image delivery, operation ordering, and current WeChat reliability live. N.E.K.O can deliver this as one plugin, but internally it must preserve those distinct responsibilities and trust boundaries.
