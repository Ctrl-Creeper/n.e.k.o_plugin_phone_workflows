from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

import pytest
from plugin.plugins.phone_workflows import READ_SCHEMA, PhoneWorkflowsPlugin
from plugin.plugins.phone_workflows._confirmation import ConfirmationGate
from plugin.plugins.phone_workflows._runtime import (
    PhoneRuntime,
    RuntimeConfig,
    action_result_payload,
    extract_images,
    foreground_from_dumpsys,
)
from plugin.plugins.phone_workflows.upstream.phone_core.backend import ActionResult

ROOT = Path(__file__).resolve().parents[1]


class _Logger:
    def warning(self, *_args, **_kwargs):
        pass

    def debug(self, *_args, **_kwargs):
        pass


class _Runtime:
    def __init__(self, result: ActionResult):
        self.result = result
        self.config = RuntimeConfig(android_serial="emulator-5554")
        self.sent = []
        self.verified = []

    async def verify_wechat_chat(self, chat: str):
        self.verified.append(chat)
        return ActionResult(ok=True, action="wechat_open_chat")

    async def send_wechat_reply(self, chat: str, text: str):
        self.sent.append((chat, text))
        return self.result

    async def selected_serial(self):
        return self.config.android_serial


class _StatusRuntime:
    def __init__(self, status: dict[str, object]):
        self._status = status

    async def status(self):
        return dict(self._status)


def _plugin(result: ActionResult) -> PhoneWorkflowsPlugin:
    plugin = object.__new__(PhoneWorkflowsPlugin)
    plugin.logger = _Logger()
    plugin._runtime = _Runtime(result)
    plugin._confirmations = ConfirmationGate()
    plugin._upstream = {"commit": "abc123"}
    return plugin


def test_plugin_manifest_and_upstream_assets_exist() -> None:
    manifest = (ROOT / "plugin.toml").read_text(encoding="utf-8")
    assert 'id = "phone_workflows"' in manifest
    assert 'entry = "plugin.plugins.phone_workflows:PhoneWorkflowsPlugin"' in manifest

    upstream = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    apk = ROOT / "assets/android/hermes-phone-agent-v0.2.4.apk"
    assert re.fullmatch(r"[0-9a-f]{40}", upstream["commit"])
    assert upstream["repository"] == "https://github.com/Ctrl-Creeper/hermes-phone-agent"
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == upstream["helper"]["sha256"]


def test_all_synchronized_file_hashes_match_manifest() -> None:
    upstream = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    for relative, expected in upstream["files"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_confirmation_is_exact_and_single_use() -> None:
    gate = ConfirmationGate()
    payload = {"chat": "Alice", "text": "hello", "device": "one"}
    token = gate.issue("reply", payload)
    assert not gate.consume(token, "reply", {**payload, "text": "changed"})

    token = gate.issue("reply", payload)
    assert gate.consume(token, "reply", payload)
    assert not gate.consume(token, "reply", payload)


def test_runtime_config_is_fail_closed() -> None:
    assert RuntimeConfig.from_mapping({"backend": "adb"}).backend == "adb"
    assert RuntimeConfig.from_mapping({"backend": "hybrid"}).backend == "hybrid"
    with pytest.raises(ValueError):
        RuntimeConfig.from_mapping({"backend": "shell"})
    with pytest.raises(ValueError):
        RuntimeConfig.from_mapping({"android_serial": "bad serial"})


def test_device_selection_requires_exactly_one_authorized_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = PhoneRuntime(RuntimeConfig(), plugin_dir=ROOT, logger=_Logger())
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/adb" if name == "adb" else None)
    monkeypatch.setenv("ANDROID_SERIAL", "environment-device-must-not-win")
    monkeypatch.setattr(
        runtime,
        "_adb_global",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["adb", "devices"],
            0,
            "List of devices attached\nemulator-5554\tdevice\nemulator-5556\tdevice\n",
            "",
        ),
    )

    with pytest.raises(RuntimeError, match="multiple authorized Android devices"):
        runtime._resolve_serial_sync()


def test_device_selection_ignores_ambient_android_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = PhoneRuntime(RuntimeConfig(), plugin_dir=ROOT, logger=_Logger())
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/adb" if name == "adb" else None)
    monkeypatch.setenv("ANDROID_SERIAL", "environment-device-must-not-win")
    monkeypatch.setattr(
        runtime,
        "_adb_global",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["adb", "devices"],
            0,
            "List of devices attached\nemulator-5554\tdevice\n",
            "",
        ),
    )

    assert runtime._resolve_serial_sync() == "emulator-5554"
    assert os.environ["ANDROID_SERIAL"] == "environment-device-must-not-win"


def test_foreground_parser_supports_new_android_activity_output() -> None:
    assert foreground_from_dumpsys(
        "topResumedActivity=ActivityRecord{77342171 u0 "
        "com.google.android.apps.nexuslauncher/.NexusLauncherActivity t2}"
    ) == "com.google.android.apps.nexuslauncher/.NexusLauncherActivity"


def test_image_extraction_removes_base64_from_model_payload() -> None:
    encoded = base64.b64encode(b"png-bytes").decode("ascii")
    payload = action_result_payload(ActionResult(
        ok=True,
        action="wechat_collect_context",
        meta={"lines": ["hello"], "screenshots": [encoded, "not-base64"]},
    ))
    images = extract_images(payload)
    assert len(images) == 1
    assert "screenshots" not in payload["meta"]
    assert images[0]["data_b64"] == encoded


@pytest.mark.asyncio
async def test_prepare_then_confirmed_send_consumes_token_once() -> None:
    plugin = _plugin(ActionResult(
        ok=True,
        action="wechat_reply",
        meta={"delivery_attempted": True, "delivery_status": "confirmed"},
    ))
    prepared = await plugin.wechat_prepare_reply(chat=" Alice ", text="收到")
    assert prepared["status"] == "clarify"
    assert prepared["chat"] == "Alice"
    assert plugin._runtime.verified == ["Alice"]

    sent = await plugin.wechat_send_confirmed(
        chat="Alice",
        text="收到",
        confirmation_token=prepared["confirmation_token"],
        confirmed=True,
    )
    assert sent["status"] == "confirmed"
    assert plugin._runtime.sent == [("Alice", "收到")]

    repeated = await plugin.wechat_send_confirmed(
        chat="Alice",
        text="收到",
        confirmation_token=prepared["confirmation_token"],
        confirmed=True,
    )
    assert repeated["error_code"] == "confirmation_required"
    assert plugin._runtime.sent == [("Alice", "收到")]


@pytest.mark.asyncio
async def test_changed_reply_cannot_use_confirmation_token() -> None:
    plugin = _plugin(ActionResult(ok=True, action="wechat_reply"))
    prepared = await plugin.wechat_prepare_reply(chat="Alice", text="one")
    result = await plugin.wechat_send_confirmed(
        chat="Alice",
        text="two",
        confirmation_token=prepared["confirmation_token"],
        confirmed=True,
    )
    assert result["error_code"] == "confirmation_required"
    assert plugin._runtime.sent == []


@pytest.mark.asyncio
async def test_changed_device_cannot_use_confirmation_token() -> None:
    plugin = _plugin(ActionResult(ok=True, action="wechat_reply"))
    prepared = await plugin.wechat_prepare_reply(chat="Alice", text="one")
    plugin._runtime.config = RuntimeConfig(android_serial="emulator-5556")
    result = await plugin.wechat_send_confirmed(
        chat="Alice",
        text="one",
        confirmation_token=prepared["confirmation_token"],
        confirmed=True,
    )
    assert result["error_code"] == "confirmation_required"
    assert plugin._runtime.sent == []


@pytest.mark.asyncio
async def test_configuration_change_rejects_prepared_runtime() -> None:
    plugin = _plugin(ActionResult(ok=True, action="wechat_reply"))
    prepared = await plugin.wechat_prepare_reply(chat="Alice", text="one")
    plugin._runtime = _Runtime(ActionResult(ok=True, action="wechat_reply"))
    plugin._confirmations = ConfirmationGate()

    result = await plugin.wechat_send_confirmed(
        chat="Alice",
        text="one",
        confirmation_token=prepared["confirmation_token"],
        confirmed=True,
    )

    assert result["error_code"] == "confirmation_required"
    assert plugin._runtime.sent == []


@pytest.mark.asyncio
async def test_uncertain_delivery_is_returned_without_retry() -> None:
    plugin = _plugin(ActionResult(
        ok=False,
        action="wechat_reply",
        message="could not verify outgoing bubble",
        meta={"delivery_attempted": True, "delivery_status": "uncertain"},
    ))
    prepared = await plugin.wechat_prepare_reply(chat="Alice", text="hello")
    result = await plugin.wechat_send_confirmed(
        chat="Alice",
        text="hello",
        confirmation_token=prepared["confirmation_token"],
        confirmed=True,
    )
    assert result["status"] == "delivery_uncertain"
    assert plugin._runtime.sent == [("Alice", "hello")]


def test_only_high_level_llm_tools_are_declared() -> None:
    names = {
        getattr(value, "__neko_llm_tool_meta__").name
        for value in PhoneWorkflowsPlugin.__dict__.values()
        if getattr(value, "__neko_llm_tool_meta__", None) is not None
    }
    assert names == {
        "phone_status",
        "wechat_read",
        "wechat_prepare_reply",
        "wechat_send_confirmed",
    }
    assert READ_SCHEMA["properties"]["max_images"]["maximum"] == 2


def test_plugin_registers_exact_high_level_tools_with_sdk_context() -> None:
    from plugin.core.context import PluginContext

    context = PluginContext(
        plugin_id="phone_workflows",
        config_path=ROOT / "plugin.toml",
        logger=logging.getLogger("phone-workflows-test"),
        status_queue=queue.Queue(),
        message_queue=queue.Queue(),
    )
    plugin = PhoneWorkflowsPlugin(context)

    assert {item["name"] for item in plugin.list_llm_tools()} == {
        "phone_status",
        "wechat_read",
        "wechat_prepare_reply",
        "wechat_send_confirmed",
    }
    registered = []
    while not context.message_queue.empty():
        message = context.message_queue.get_nowait()
        if message.get("type") == "LLM_TOOL_REGISTER":
            registered.append(message["name"])
    assert set(registered) == {
        "phone_status",
        "wechat_read",
        "wechat_prepare_reply",
        "wechat_send_confirmed",
    }


@pytest.mark.asyncio
async def test_phone_status_requires_expected_helper_version() -> None:
    plugin = object.__new__(PhoneWorkflowsPlugin)
    plugin.logger = _Logger()
    plugin._upstream = {"helper": {"version": "0.2.4"}}
    plugin._runtime = _StatusRuntime({
        "connected": True,
        "helper_installed": True,
        "helper_version": "0.2.3",
    })

    result = await plugin.phone_status()

    assert result["status"] == "needs_setup"
    assert result["workflow_ready"] is False
    assert result["setup_required"] == ["update_helper"]


@pytest.mark.asyncio
async def test_setup_confirmation_requires_one_actual_device() -> None:
    plugin = object.__new__(PhoneWorkflowsPlugin)
    plugin.logger = _Logger()
    plugin._upstream = {"helper": {"sha256": "abc"}}
    plugin._runtime = _StatusRuntime({
        "connected": False,
        "error_code": "device_ambiguous",
        "authorized_devices": ["one", "two"],
    })
    plugin._confirmations = ConfirmationGate()

    result = await plugin.setup_action("install_helper")

    assert result.value["status"] == "needs_setup"
    assert "confirmation_token" not in result.value


@pytest.mark.asyncio
async def test_phone_operations_are_serialized(monkeypatch: pytest.MonkeyPatch) -> None:
    from plugin.plugins.phone_workflows.upstream.phone_core import wechat

    runtime = PhoneRuntime(RuntimeConfig(), plugin_dir=ROOT, logger=_Logger())
    runtime._backend = object()
    state = {"active": 0, "maximum": 0}
    guard = threading.Lock()

    def fake_reply(_backend, chat: str, text: str):
        with guard:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
        time.sleep(0.03)
        with guard:
            state["active"] -= 1
        return ActionResult(ok=True, action="wechat_reply", message=f"{chat}:{text}")

    monkeypatch.setattr(wechat, "reply", fake_reply)
    await asyncio.gather(
        runtime.send_wechat_reply("one", "a"),
        runtime.send_wechat_reply("two", "b"),
    )
    assert state["maximum"] == 1


@pytest.mark.asyncio
async def test_setup_and_phone_operations_share_one_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugin.plugins.phone_workflows.upstream.phone_core import wechat

    runtime = PhoneRuntime(RuntimeConfig(), plugin_dir=ROOT, logger=_Logger())
    runtime._backend = object()
    state = {"active": 0, "maximum": 0}
    guard = threading.Lock()

    def enter_operation():
        with guard:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
        time.sleep(0.03)
        with guard:
            state["active"] -= 1

    def fake_reply(_backend, _chat: str, _text: str):
        enter_operation()
        return ActionResult(ok=True, action="wechat_reply")

    def fake_adb(*_args, **_kwargs):
        enter_operation()
        return subprocess.CompletedProcess(["adb"], 0, "", "")

    monkeypatch.setattr(wechat, "reply", fake_reply)
    monkeypatch.setattr(runtime, "_resolve_serial_sync", lambda: "emulator-5554")
    monkeypatch.setattr(runtime, "_adb", fake_adb)

    await asyncio.gather(
        runtime.send_wechat_reply("one", "a"),
        runtime.grant_notification_listener("emulator-5554"),
    )

    assert state["maximum"] == 1


@pytest.mark.asyncio
async def test_ocr_compile_failure_is_a_degraded_startup_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "phone_ocr.swift"
    source.write_text("invalid swift", encoding="utf-8")
    runtime = PhoneRuntime(
        RuntimeConfig(ocr_helper_path=str(tmp_path / "phone-ocr")),
        plugin_dir=ROOT,
        logger=_Logger(),
    )
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/swiftc" if name == "swiftc" else None)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["swiftc"], 1, "", "failed"),
    )

    result = await runtime.ensure_ocr_helper(source)

    assert result == {"status": "failed", "reason": "compile_failed"}


@pytest.mark.asyncio
async def test_context_collection_returns_home_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugin.plugins.phone_workflows.upstream.phone_core import wechat_context

    class Backend:
        def __init__(self):
            self.keys = []

        def keyevent(self, key: str):
            self.keys.append(key)
            return ActionResult(ok=True, action="keyevent")

    backend = Backend()
    runtime = PhoneRuntime(RuntimeConfig(), plugin_dir=ROOT, logger=_Logger())
    runtime._backend = backend

    def fail(_backend, **_kwargs):
        raise RuntimeError("capture failed")

    monkeypatch.setattr(wechat_context, "collect_context", fail)
    with pytest.raises(RuntimeError, match="capture failed"):
        await runtime.collect_wechat_context(chat="Alice")
    assert backend.keys == ["HOME"]
