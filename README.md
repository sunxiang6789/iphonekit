# iphone-agent-kit

**让 AI 助手（Claude Code / Codex）替你操作 iPhone：说一句话，它就去点、去查、去办，办完推送结果到你手机上。**

> 📺 演示视频：（待补，发布时放链接）

基于开源项目 [iphone-use](https://github.com/leeguooooo/iphone-use)（作者 [leeguooooo](https://github.com/leeguooooo)）。本仓库只是它外面的一层「胶水」：一键安装、快捷指令下命令、Bark 推送结果、规则模板和 App 笔记。

## 一条命令安装

在 Mac 上打开「终端」，粘贴：

```bash
curl -fsSL https://raw.githubusercontent.com/sunxiang6789/sunxiang-ai/main/install.sh | bash
```

装完跟着向导回答几个问题就好，全程中文。

### 🤖 更省事：让你电脑上的 AI 助手帮你装

已经有 Claude Code 或 Codex 的话，打开它，把下面这句发给它就行（它会自己读本页的说明、跑安装、补装缺的东西；需要你动手的地方，比如输 Mac 密码、手机上点“信任”，会一步一步告诉你）：

```
帮我安装 https://github.com/sunxiang6789/sunxiang-ai ，照它 README 里“让助手帮你装”做。我是小白，需要我动手的地方一步步告诉我。
```

也可以在终端一行搞定（Codex 把 `claude` 换成 `codex`；**不要加 `-p`**，那是一次性模式，没法中途等你操作）：

```bash
claude "帮我安装 https://github.com/sunxiang6789/sunxiang-ai ，照它 README 里“让助手帮你装”做。我是小白，需要我动手的地方一步步告诉我。"
```

<details>
<summary>助手照着做的详细步骤（助手读这里；你不用看）</summary>

```
请帮我安装 iphone-agent-kit（让 AI 操控 iPhone 的工具），我是电脑小白，别问我技术问题，直接处理。
1. 在终端运行：curl -fsSL https://raw.githubusercontent.com/sunxiang6789/sunxiang-ai/main/install.sh | bash
2. 安装向导里的选项，按推荐的默认来：使用方式选“两个都要”，纯小白模式开，外卖直接付款关；Bark key 我稍后给你，没有就先留空。
3. 缺什么就帮我装（助手命令行版 claude / codex、Xcode 路径有空格的问题、PATH 等）。
4. 需要我动手的地方（输 Mac 开机密码、iPhone 点“信任”、打开开发者模式、在 Xcode 登录 Apple ID、装 Bark 拿 key），用大白话一步一步告诉我怎么做，做完等我回你。
5. 全部装完运行 iphone-agent-kit doctor 体检，把结果和下一步告诉我。
```

</details>

## 开始前要准备的

| 要什么 | 说明 |
|---|---|
| 一台 Mac | Apple 芯片或 Intel 都行，macOS 要比较新（能装当前版 Xcode） |
| 一台 iPhone | 被操控的手机，用数据线连 Mac（之后可以无线） |
| 完整版 Xcode | 去 Mac App Store 免费下载（十几 G，提前下好）。只装「命令行工具」不够 |
| Apple ID | 免费的就行，在 Xcode 里登录，用来给 iPhone 上的程序签名 |
| Bark | iPhone 上的免费推送 App（App Store 搜「Bark」），用来收结果 |
| Claude Code 或 Codex | 至少一个，命令行版。Claude Code 要先 `claude auth login` 登录 |

**不支持 Windows / Linux**：iphone-use 要靠 Xcode 往 iPhone 上装一个测试程序来点屏幕，而 Xcode 只有 Mac 有。

## 安装时会发生什么

### 安装脚本（5 步）

1. **检查环境**：macOS、芯片、Python 3、时区、Xcode。缺什么会直接告诉你去哪装。
2. **安装程序文件**：放到 `~/.local/share/iphone-agent-kit/`，命令 `iphone-agent-kit` 链到 `~/.local/bin/`。如果提示「不在 PATH 里」，照它打印的那行加进 `~/.zshrc` 再重开终端。重复运行安装命令 = 更新。
3. **检查 Xcode 路径**：Xcode 放在带空格的路径里（比如外接硬盘「My Disk」）iphone-use 会失败，这一步会自动建一个不带空格的 `/Applications/Xcode.app` 替身；然后它会打印一条 `sudo xcode-select -s …`，**你要自己复制运行并输 Mac 开机密码**。
4. **安装 iphone-use**：调用 iphone-use 官方安装脚本，再跑它的设置。这一步要你动手：
   - iPhone 用数据线连上 Mac，手机上弹「要信任此电脑吗」→ 点**信任**，输锁屏密码。
   - iPhone 打开**开发者模式**：设置 → 隐私与安全性 → 开发者模式 → 打开，手机会重启，重启后再点一次「打开」。（看不到这一项的话，先在 Xcode 里连一次手机，它就会出现。）
   - Xcode → 设置 → Accounts → 左下角「+」登录你的 Apple ID。
   - 第一次装到手机上后，iPhone 要去 设置 → 通用 → VPN 与设备管理 → 点你的 Apple ID → **信任**。
5. **安装向导**：见下面。

### 安装向导（8 步，之后也可以随时运行 `iphone-agent-kit init` 重来）

1. **选使用方式 + 纯小白模式**：A（助手自己的手机 App 远程连电脑）、B（快捷指令说一句话）或**两个都要（默认推荐）**。只选 A 时不装后台服务、不需要快捷指令，Bark 也变成可选；选了 B 或都要，Bark 必配。紧接着问**要不要开纯小白模式**（默认开）：开了以后，助手每次停下来要你动手（付款、刷脸、点信任、登录……），都会用大白话一步一步告诉你「现在要做什么、点哪里、做完怎么办」，Bark 推送也一样。以后想改，重跑 `iphone-agent-kit init` 就行。
2. **选 AI 助手**：Claude Code、Codex 或两个都要。选了 Claude Code 但还没登录，会提示你运行 `claude auth login`。
   - **选了 B（或都要）时，向导会先讲清楚**：后台服务要用助手的「命令行版」（在 Mac 的「终端」里运行的 `claude` / `codex`），和平时点开的桌面版不是一回事。
   - 检测到你只装了桌面版（或什么都没装）时，会问你**要不要帮你装命令行版**（Claude Code 用官方安装脚本；Codex 用 npm 或 Homebrew）。你说不装也行，桌面版自带的那份通常能借来用，只是桌面版更新后偶尔会失效。
   - 不想自己操心的话，直接对你电脑上的助手说「帮我装好 claude / codex 命令行版」就行，见上面的「卡住了？」。
3. **Bark**（选 B 必配，只选 A 可选）：iPhone 装好 Bark 打开，首页会显示一个网址，形如 `https://api.day.app/一串字母/…`，中间那串就是 key。把整个网址粘贴进来也行。快捷指令只回你一句「好的，我去办」，**做完的结果全靠 Bark 推送**，所以别跳过。
4. **人设「小柚」**：默认开，推送是 18 岁台湾女生的口吻（「弄好啦～」）。不喜欢就选关，变成正常语气。
5. **外卖直接付款**：默认关，建议保持关。详见 [安全提示](#安全提示)。
6. **签名到期提醒**：免费 Apple ID 签的程序 7 天过期，开了之后每天检查一次，剩 2 天时用 Bark 提醒你。
7. **生成配置和文件**：配置放在 `~/.config/iphone-agent-kit/`；会把操作手机的规则写进 `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`——**写之前会先问你**，只写在一段 `<!-- iphone-agent-kit:start -->…<!-- iphone-agent-kit:end -->` 标记里，你自己写的内容不动，改之前会备份。
8. **注册后台服务**：桥接服务开机自启，快捷指令发来的任务由它接（只选 A 时跳过）。

装完运行一下体检，全绿就能用了：

```bash
iphone-agent-kit doctor
```

## 🆘 卡住了？让你电脑上的 AI 助手帮你

你已经有 Claude Code 或 Codex 了，**装不上、报错、不知道下一步，都不用自己琢磨**：打开它，把下面这段话原样发给它，它会自己检查、安装、修复，需要你动手的地方（输 Mac 密码、手机上点“信任”等）会一步一步告诉你怎么做。

```
我在装 iphone-agent-kit（让 AI 操控 iPhone 的工具）。请你帮我：
1. 运行 iphone-agent-kit doctor 体检，看哪里不对；
2. 缺什么就帮我装（比如助手的命令行版 claude / codex、Xcode 路径空格问题、Bark 配置），遇到要我输密码或在手机上点的，用大白话一步一步告诉我怎么做；
3. 全部正常后，告诉我下一步该做什么。
我是电脑小白，别问我技术问题，直接帮我处理。
```

特别是这几件事，**交给助手最省事**：安装助手的命令行版（`claude` / `codex`）、给 Mac 加 `~/.local/bin` 到 PATH、处理 Xcode 路径带空格、排查 `doctor` 里的 ⚠️ 和 ❌。

## 两种用法（装的时候选 A、B 或都要）

### 方式 B（推荐）：快捷指令说一句话

适合只有命令行的助手（Claude Code 命令行、Codex 命令行），也适合任何人——**不用开电脑屏幕，拿起手机说话就行。**

1. 在 Mac 上生成快捷指令：

   ```bash
   iphone-agent-kit shortcuts
   ```

   它会在桌面建一个 `iphone-agent-kit-shortcuts` 文件夹并打开。
2. 把里面的「让手机做事」**隔空投送**到你自己（下命令用）的 iPhone 上，点「添加快捷指令」。
3. 说「嘿 Siri，让手机做事」，或者点快捷指令，然后说要办的事，例如：
   - 「看看手机还剩多少空间」
   - 「给文件传输助手发一句我到了」
   - 「用 Opus，帮我比一下这三款耳机哪个划算」
4. 快捷指令只回你一句「好的，我去办」（开着人设是小柚的「好喔，我去弄～」），**不会等结果**。做完、办不成、需要你付款时，Bark 会推送到你手机上。
5. 想叫停：再运行一次快捷指令，说「**停止**」或「**别弄了**」。

小技巧：

- 句子开头说「用 Codex，……」「用 Claude，……」可以临时换助手；用 Claude 时说「用 Opus，……」（要动脑的事）或「用 Sonnet，……」（简单的事）可以指定模型，不说就自动判断。
- 下命令的手机和被控的手机可以是同一台，也可以是两台。
- 只有一个快捷指令就够了，不需要别的。

### 方式 A：用助手自己的手机 App

有些助手有自己的手机 App，可以「远程连」电脑上正在运行的助手。这样你在手机上和它聊天，电脑上的它去操控 iPhone。这种方式**不需要快捷指令和桥接服务**，只需要装好 iphone-use，并让向导把规则写进 `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`。

各家支持情况见 [docs/方式A-助手手机端.md](docs/方式A-助手手机端.md)（会变，以官方为准）。

## 命令速查

| 命令 | 做什么 |
|---|---|
| `iphone-agent-kit init` | 重新跑安装向导（改设置用这个） |
| `iphone-agent-kit doctor` | 体检：每项 ✅ / ⚠️ / ❌，并告诉你怎么修 |
| `iphone-agent-kit resign` | 重新给 iPhone 上的程序签名（7 天到期时用）；`--mark-now` 只记下「刚签过」 |
| `iphone-agent-kit shortcuts` | 生成快捷指令到桌面；`--url` 指定地址（比如用 Tailscale 时） |
| `iphone-agent-kit status` | 看后台服务在不在跑、在做什么 |
| `iphone-agent-kit restart` | 重启后台服务（改了配置后用） |
| `iphone-agent-kit logs` | 看日志；`-f` 持续看 |
| `iphone-agent-kit token` | 打印令牌（快捷指令里用的那串，别外传） |
| `iphone-agent-kit fix-xcode` | Xcode 路径有空格时建替身 |
| `iphone-agent-kit uninstall` | 卸载（不会动 iphone-use 本体） |

## 常见问题

出问题先跑 `iphone-agent-kit doctor`。按现象查：[docs/常见问题.md](docs/常见问题.md)，里面有 Xcode 路径空格、时区、手机被占用、7 天签名到期、Claude 没登录、Bark 收不到、手机连不上、不在家怎么用、模型名不可用等。

## 安全提示

- **快捷指令里带着你的令牌**，相当于遥控你手机的钥匙。只在自己 Mac 上生成，**不要把快捷指令或令牌发给别人**。泄露了就删掉 `~/.config/iphone-agent-kit/config.json` 里的 `token`，运行 `iphone-agent-kit restart`（会生成新令牌），再重新 `shortcuts`。
- **付款由你自己点**：任何付款、转账、购买、充值，以及需要你本人确认的操作，AI 只做到付款/确认页面就停下，推送告诉你付给谁、多少钱，然后退出自动控制，由你自己在手机上付。这是默认规则。
- **外卖直接付款**是可选项，默认关。打开后 AI 会不问你直接下单付款，可能点错、多付小额费用，钱不一定能退。开之前读完 [templates/optional/takeout-direct-pay.md](templates/optional/takeout-direct-pay.md)，向导里要输入「我接受风险」才会打开。
- 桥接服务**只接受局域网、Tailscale、USB 连接**发来的请求，外网直接拒绝。
- **永远不要把支付密码、银行卡号、验证码告诉 AI**，也不要把被控手机设成免密支付。需要刷脸或输密码时 AI 会停下来叫你。
- 被控手机上的东西 AI 都看得到（屏幕内容会发给 AI 服务商处理），隐私内容自己掂量。

## 自定义

- **个人档案** `~/.config/iphone-agent-kit/profile.md`：写称呼、常用地址（写到区就够）、口味、预算、常用 App。AI 做选择前会先读它，遇到档案里没有又必须知道的会问你一次并自己补进去。别写密码、卡号、身份证号。
- **关掉人设**：重跑 `iphone-agent-kit init` 选「关」；或者把 `config.json` 里的 `"persona": {"enabled": false}`，再 `iphone-agent-kit restart`。
- **改规则**：快捷指令那条路的规则在 `templates/rules.md`，直接对话用的在 `templates/agent-rules.md`。想改就把同名文件复制到 `~/.config/iphone-agent-kit/` 再改，会优先用你那份。
- **App 笔记** `app-notes/包名.md`：告诉 AI 某个 App 的按钮大概在哪、有什么坑，能让它少试探、快很多。安装时会写进 iphone-use。格式参考 [app-notes/com.meituan.itakeaway.md](app-notes/com.meituan.itakeaway.md)，开头写清机型、iOS 版本、记录日期。**欢迎提 PR 分享你的 App 笔记！**
- 其他设置（端口、Bark 服务器、模型、超时）见 [config.example.json](config.example.json)，只写你想改的项。

## 致谢与许可证

- 操控 iPhone 的核心能力来自 [iphone-use](https://github.com/leeguooooo/iphone-use)，作者 [leeguooooo](https://github.com/leeguooooo)，使用 [PolyForm Shield](https://polyformproject.org/licenses/shield/1.0.0/) 许可。本仓库**不包含、不修改、不分发** iphone-use 的代码，安装时只调用它官方的安装脚本。
- 测试过的 iphone-use 版本：**0.19.1**。iphone-use 更新很快，新版本如果不兼容，欢迎提 Issue。
- 本仓库自己的代码使用 [MIT 许可](LICENSE)。非商业项目。
