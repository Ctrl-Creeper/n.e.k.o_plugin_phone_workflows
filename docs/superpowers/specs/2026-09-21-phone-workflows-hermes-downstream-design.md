# Phone Workflows Hermes-Downstream Design

## Decision

`hermes-phone-agent` is the canonical phone implementation. The N.E.K.O
plugin and `phone-mcp-server` are independent downstream projections:

```text
hermes-phone-agent
  +-- phone-mcp-server: MCP and HTTP transports
  +-- phone_workflows: N.E.K.O tools, confirmation, setup, UI, and events
```

N.E.K.O does not inherit phone behavior through the older MCP snapshot. It
synchronizes the host-neutral core directly and records the exact upstream
commit and hashes. Raw phone operations remain private implementation detail.

## First Release

The plugin contains:

- byte-identical synchronized ADB, Appium, OCR, policy, and WeChat modules;
- the canonical Helper APK with a pinned SHA-256;
- one serialized device runtime;
- status and bounded WeChat context tools;
- separate prepare and confirmed-send tools;
- staged setup actions for APK installation, Notification Listener, and
  Accessibility.

Only four model tools are registered. Setup mutations are ordinary plugin
entries and therefore never become model-callable.

## Confirmation Contract

Preparing a reply verifies the exact conversation but never sends. It issues a
cryptographically random, short-lived token bound to:

- the action;
- configured device serial or the single-device selector;
- normalized conversation title;
- exact message text;
- synchronized upstream revision.

The token is consumed before device mutation. Payload mismatch, expiry,
restart, configuration change, or reuse requires a new preparation. Current
N.E.K.O `@llm_tool` callbacks do not provide a conversation identifier, so the
token cannot yet be bound to a host conversation ID; its unguessable capability
and exact-payload binding are the current enforcement boundary.

## Delivery Contract

The canonical Hermes workflow may retry navigation before attempting a send.
After any possible send attempt, the plugin returns exactly one of:

- `confirmed`;
- `delivery_uncertain`;
- `not_attempted`.

The plugin never retries `delivery_uncertain`.

## Helper and Permissions

Installing the APK enables the ADB-protected clipboard path used for Unicode
and shell-sensitive text. It does not grant event access. Notification Listener
and Accessibility remain separate confirmation-gated setup actions.

On macOS, the synchronized Vision OCR source is compiled into plugin-owned
data storage. No files are written under `~/.hermes` or `~/.phone-mcp`.

## Events

Authenticated phone events remain phase two. The same plugin will synchronize
the host-neutral socket authentication, event model, filtering, and redaction
from Hermes, then route them through N.E.K.O `push_message`. Event permissions
and automatic task-source rules remain disabled by default.
