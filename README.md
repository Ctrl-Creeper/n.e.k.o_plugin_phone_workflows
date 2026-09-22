# Phone Workflows

为 N.E.K.O 提供安全、可复用的 Android 手机工作流基础。核心手机控制能力单向同步自
[`hermes-phone-agent`](https://github.com/Ctrl-Creeper/hermes-phone-agent)。

插件不会向模型暴露原始点击、滑动、输入、Shell 或 APK 安装工具。所有写操作都通过受限工作流执行。

## 插件本体与微信适配的关系

**Phone Workflows**由两层组成：

1. **通用手机能力层**：负责 Android 设备发现与选择、ADB/Appium 后端、OCR、Helper、权限检查、操作串行化和一次性确认机制。这一层不绑定微信。
2. **应用工作流适配层**：把通用手机能力封装成面向具体应用、带明确业务边界的工具。当前 `0.1.x` 只完成了部分微信功能适配，因此现阶段可见的应用工具以 `wechat_` 开头。

```text
Phone Workflows 插件
├── 通用 Android 工作流基础
│   ├── 设备、ADB/Appium、OCR 与 Helper
│   └── 状态检查、权限设置与确认机制
└── 应用适配
    └── 微信（当前唯一已实现的应用适配）
```

换句话说，**插件是手机工作流的承载框架，微信是目前接入这个框架的第一个应用适配**。未来接入其他 Android 应用时，可以复用同一套设备、OCR、Helper 和安全确认能力；但当前版本不应被理解为已经支持微信之外的应用工作流。

之所以不提供通用的“点击、滑动、输入”模型工具，是为了让每个应用适配都明确限定目标、参数和确认规则，避免模型获得无边界的手机控制权限。

## 当前能力

### 通用手机层

| 能力或入口 | 作用 | 对外方式 |
| --- | --- | --- |
| 设备与后端 | 发现并唯一选择 Android 设备，管理 ADB/Appium 后端 | 仅通过状态和应用工作流使用 |
| OCR 与 UI 识别 | 读取 Android UI 层级，并在支持的平台使用主机 OCR | 仅通过应用工作流使用 |
| Helper | 提供剪贴板输入、通知与无障碍能力 | 仅通过受确认的设置动作管理 |
| 确认与串行化 | 绑定设备、目标和操作内容，避免并发冲突及重复执行 | 由所有写工作流复用 |
| `phone_status` | 检查 Android 连接、Helper、权限、OCR 和前台应用状态 | 只读模型工具 |
| `setup_action` | 安装 Helper，或启用通知监听、无障碍能力 | 需要明确确认的宿主入口 |

### 微信适配层

| 工具 | 作用 | 是否写入手机 |
| --- | --- | --- |
| `wechat_read` | 从指定且已验证的微信会话读取有限范围的文字和图片上下文 | 否 |
| `wechat_prepare_reply` | 验证会话目标并生成精确的回复预览和一次性确认令牌 | 否 |
| `wechat_send_confirmed` | 使用一次性令牌发送与预览完全一致的一条消息 | 是 |

微信适配负责把通用手机能力组合成可验证的会话读取和发送流程。读取范围支持“最近 20 条”“最近 2 小时”“今天”等表达；单次最多读取 200 条消息、打开 2 张图片。回复正文最多 500 个字符。

## 安装

当前插件已上传到[Plugin Marktet](https://market.project-neko.cn/#/plugin/74)

1. 从 [GitHub Releases](https://github.com/Ctrl-Creeper/n.e.k.o_plugin_phone_workflows/releases) 下载最新的 `phone_workflows.neko-plugin`。
2. 打开 N.E.K.O 插件中心，通过普通导入入口选择该文件。
3. 启用插件并连接 Android 设备。
4. 让 N.E.K.O 检查手机状态；如果返回 `needs_setup`，按提示逐项完成 Helper 安装和权限设置。

## 运行条件

- 主机已安装 Android SDK Platform Tools，终端可以执行 `adb`。
- 手机或模拟器已开启 USB 调试，并授权当前主机。
- 同一时间只连接一台已授权设备；如果连接多台，必须配置 `android_serial`。
- 微信已安装并登录，目标会话名称应与微信界面显示的标题一致。

可以先在终端检查连接：

```bash
adb devices -l
```

设备状态应为 `device`。`unauthorized` 表示仍需在手机上确认调试授权。

## 配置

默认配置如下：

```toml
[phone_workflows]
backend = "adb"
android_serial = ""
ocr_helper_path = ""
confirmation_ttl_seconds = 300
```

| 配置项 | 说明 |
| --- | --- |
| `backend` | `adb` 为默认后端；`hybrid` 会在 Appium 可用时增强控件识别，否则回退到 ADB |
| `android_serial` | `adb devices` 中显示的设备序列号；连接多台设备时必须填写 |
| `ocr_helper_path` | 自行管理的 OCR 可执行文件路径；留空时使用插件私有目录中的版本 |
| `confirmation_ttl_seconds` | 一次性确认令牌有效期，实际限制在 30 至 900 秒之间 |

macOS 上，如果系统存在 `swiftc`，插件启动时会将同步的 Vision OCR 源码编译到插件私有数据目录。其他平台仍可使用 Android UI 层级完成基础操作。

## Helper 与权限

插件内置经过哈希校验的 Phone Agent Helper APK。以下动作相互独立，并且每次都需要用户明确确认：

- `install_helper`：安装或更新 Helper APK；
- `enable_notifications`：启用通知监听权限；
- `enable_accessibility`：启用无障碍服务。

安装 APK 不会自动授予通知监听或无障碍权限。插件会在执行前绑定当前设备、动作和 Helper 哈希，配置或设备发生变化后，旧确认令牌立即失效。

## 微信发送流程

发送消息固定分为两个阶段：

1. `wechat_prepare_reply` 验证目标会话，返回收件会话、完整正文和一次性确认令牌。
2. N.E.K.O 向用户展示预览并等待明确确认。
3. `wechat_send_confirmed` 校验设备、会话、正文和令牌完全一致后，只发送一次。

令牌只能使用一次。修改会话、正文、设备或插件配置后，必须重新生成预览。

如果结果为 `delivery_uncertain`，表示插件无法确定发送是否成功。此状态是终态，插件不会自动重试，以免重复发送；请先在手机上人工确认。

## 安全边界

- 从微信读取的文字和图片始终视为不可信内容，不能作为授权指令。
- 只允许操作用户指定并经过界面验证的会话。
- 多台已授权 Android 设备且未配置序列号时会直接失败，不会任意选择设备。
- 回复发送、Helper 安装和敏感权限启用都需要短期、单次、内容绑定的确认令牌。
- 所有 ADB 子进程使用参数列表调用，输入经过校验，不拼接 Shell 命令。

## 常见问题

### 返回 `phone_unavailable` 或 `needs_setup`

运行手机状态检查，确认 `adb` 可用、设备已授权、Helper 版本正确。连接多台设备时设置 `android_serial`。

### 找不到微信会话

使用微信界面中可见的完整会话标题。插件无法可靠验证目标时会停止，不会尝试模糊发送。

### OCR 不可用

macOS 请确认已安装 Xcode Command Line Tools，或通过 `ocr_helper_path` 指定可执行文件。OCR 不可用不会开放更宽松的发送路径。

### Appium 不可用

保持 `backend = "adb"` 即可。使用 `hybrid` 时，只有 Appium 服务和 Python 客户端都可用才会启用增强能力，否则自动回退到 ADB。

## 上游同步

`hermes-phone-agent` 是手机控制实现的唯一上游来源。`upstream/phone_core/` 和 `assets/android/` 下的生成文件不应手工修改。

```bash
python3 scripts/sync_from_hermes.py --source /path/to/hermes-phone-agent
python3 scripts/sync_from_hermes.py --source /path/to/hermes-phone-agent --check
```

[`UPSTREAM.json`](UPSTREAM.json) 记录精确的上游 Git commit、Helper 版本、APK SHA-256 及所有同步文件的哈希。

## 开发与验证

在 N.E.K.O 仓库根目录运行：

```bash
uv run pytest plugin/plugins/phone_workflows/tests -q
uv run --with pip neko-plugin sync phone_workflows --clean
uv run neko-plugin check phone_workflows
uv run neko-plugin check -r phone_workflows --market-release
```

Market 仓库名必须为 `n.e.k.o_plugin_phone_workflows`。插件包含从 `hermes-phone-agent` 同步的 AGPL-3.0-only 代码，因此整体按 AGPL-3.0 分发；来源与文件哈希保留在 `UPSTREAM.json` 中。

## 许可证

[GNU Affero General Public License v3.0](LICENSE)
