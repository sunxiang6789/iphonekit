# iphone-agent-kit

![躺着，AI 替你点手机](docs/assets/cover.png)

**按一下 iPhone 侧边按钮，说一句话，Mac 上的 AI 就替你把手机点完。做完了，推送告诉你。**

> 📺 演示视频：（待补，发布时放链接）

我一直想要这么个东西：人躺着，让 AI 去点我的手机。

查手机还剩多少空间，给文件传输助手发一句“我到了”，把刚看的页面整理进备忘录……这些事 AI 早就会干。烦的是每次都得先坐回电脑前，开终端，敲一句话，再盯着屏幕等。

所以我把中间这一截补上了。现在是这样：

> 按住侧边按钮 → 说“看看手机还剩多少空间” → 手机揣回兜里 → 十几秒后 Bark 弹出一条：“还剩 200 多 G 啦，放心用～”

全程没打开任何 App，也没碰电脑。

## 三个我自己最在意的点

**一、按一下就开工，快。**
走的是 iPhone 系统自带的快捷指令，不是某个要你先点开的 App。侧边按钮、主屏幕图标、对 Siri 说一声，都行。

- 回一句“收到”，大约 1.5 秒。
- 问“现在几点”“37 乘 12”这种用不着手机的小问题，小模型直接答，大约 1.5 秒，只推一条，不会再叫醒大模型来重复答一遍。
- 真要操作手机的任务，我现在用 dsh + 水星 3：查手机剩余空间，热启动 13 秒左右，冷启动 26 秒左右。
- 做完一件事后 30 分钟内，下一句话会接着上次聊。你可以直接说“把刚才整理的放进备忘录”。
- 手机锁屏了，会推送叫你解锁；解锁完说一句“解锁了”，它接着做，不会从头来。

（以上是我在自己的 iPhone 17 Pro 上量的小样本，只能说明大致快慢，换手机换网络会不一样。）

**二、小白也能装好。**
装这类东西最劝退人的是那一长串：Xcode、Apple ID、开发者模式、信任电脑、签名……所以我没写成一份让你照着敲的教程，而是写了一份给 AI 助手读的安装指南。你把一句话发给电脑上的 Claude Code、Codex 或 DeepSeek Harness，它自己检查环境、一步步装，该你动手的地方（输 Mac 密码、手机上点“信任”、点“获取”刷脸），它会用大白话告诉你点哪里。连 Bark 都是它打开页面，你只管点一下。

**三、做完自动推送。**
收到了、做完了、它有话要问你、手机该解锁了、到了付款页该你自己付——每一种情况都有一条推送，你不用守着屏幕。

基于开源项目 [iphone-use](https://github.com/leeguooooo/iphone-use)（作者 [leeguooooo](https://github.com/leeguooooo)）。我只是在它外面包了一层：一键安装、快捷指令、Bark 推送、规则模板和 App 笔记。

## 怎么用（装好之后）

**主推：iPhone 侧边操作按钮**（iPhone 15 Pro 及以上）：设置 → 操作按钮 → 快捷指令 → 选“让手机做事”。以后按住侧边按钮就说话，松开就去办。
**也可以放主屏幕**：把“让手机做事”添加到主屏幕，点图标说话；或者对 Siri 说“让手机做事”。

说什么都行，例如：
- “看看手机还剩多少空间”
- “给文件传输助手发一句我到了”
- “用 Opus，帮我比一下这三款耳机哪个划算”

小技巧：
- 说“停止”或“别弄了”可以叫停。
- 说“新任务：……”另起一件事，不接上一件。
- 句子开头说“用 Codex，……”“用 Claude，……”“用 DeepSeek，……”可以临时换助手；用 Claude 时说“用 Opus，……”（要动脑的事）或“用 Sonnet，……”（简单的事）可以指定模型。
- 想关掉简单问题直答：`config.json` 里写 `"ack": {"quick_answer": false}`。

**补充用法（助手本来就有的能力）**：如果你用的助手有官方手机控制端（能在手机 App 里远程连电脑上正在跑的会话），也可以直接在那个 App 里下命令。**使用的前提是该助手有手机控制端**，见 [docs/助手手机App远程用.md](docs/助手手机App远程用.md)。没有的话，用快捷指令就够了。

## 一键安装

### 🤖 推荐：让你电脑上的 AI 助手帮你装

已经有 Claude Code、Codex 或 DeepSeek Harness 的话，打开它，把下面这句发给它就行。它会自己读安装指南、跑安装、补装缺的东西；需要你动手的地方（输 Mac 密码、手机上点“信任”、装 Bark……）会一步一步告诉你：

```
帮我安装 https://github.com/sunxiang6789/sunxiang-ai ，先读仓库里的 AGENT_INSTALL.md，照它做。我是小白，需要我动手的地方一步步告诉我。
```

也可以在终端一行搞定（Codex 把 `claude` 换成 `codex`；**不要加 `-p`**，那是一次性模式，没法中途等你操作）：

```bash
claude "帮我安装 https://github.com/sunxiang6789/sunxiang-ai ，先读仓库里的 AGENT_INSTALL.md，照它做。我是小白，需要我动手的地方一步步告诉我。"
```

### 自己动手：一条命令

在 Mac 上打开“终端”，粘贴：

```bash
curl -fsSL https://raw.githubusercontent.com/sunxiang6789/sunxiang-ai/main/install.sh | bash
```

装完跟着向导回答几个问题就好，全程中文。

## 开始前要准备的

| 要什么 | 说明 |
|---|---|
| 一台 Mac | Apple 芯片或 Intel 都行，macOS 要比较新（能装当前版 Xcode） |
| 一台 iPhone | 被操控的手机，用数据线连 Mac（之后可以无线）。想用侧边操作按钮需要 iPhone 15 Pro 及以上 |
| 完整版 Xcode | 去 Mac App Store 免费下载（十几 G，提前下好）。只装“命令行工具”不够 |
| Apple ID | 免费的就行，在 Xcode 里登录，用来给 iPhone 上的程序签名 |
| Bark | iPhone 上的免费推送 App，用来收结果，必装。认准：**Bark - 给你的手机发推送**，开发者“丰 黄”（Finb），红色图标、白色蝴蝶结形图案，App Store 链接 `apps.apple.com/app/id1403753865`；名字相近的别的 App 不要装。用 AI 助手引导安装时，手机连上后它会帮你打开这个页面，你只需点“获取”并刷脸 |
| 一个 AI 助手的命令行版 | **推荐 DeepSeek Harness 的 `dsh`**（先在桌面版 Models 页保存好 API key）；也可以 Claude Code（要先 `claude auth login`）或 Codex |

**不支持 Windows / Linux**：iphone-use 要靠 Xcode 往 iPhone 上装一个测试程序来点屏幕，而 Xcode 只有 Mac 有。

## 推荐版本

- **iphone-use：v0.19.1**。本工具一直在这个版本上测试和使用，`install.sh` 会固定装这个版本；已装其他版本只会提醒，不会擅自降级；`doctor` 会提示版本不一致。AI 助手引导模式（AGENT_INSTALL.md）里也是这样处理。
- **助手：DeepSeek Harness 的命令行 `dsh`**。启动最快，在桌面版里保存好 API key 即可，见下面“推荐使用”。

## 安装时会发生什么

### 安装脚本（5 步）

1. **检查环境**：macOS、芯片、Python 3、时区、Xcode。缺什么会直接告诉你去哪装。
2. **安装程序文件**：放到 `~/.local/share/iphone-agent-kit/`，命令 `iphone-agent-kit` 链到 `~/.local/bin/`。如果提示“不在 PATH 里”，照它打印的那行加进 `~/.zshrc` 再重开终端。重复运行安装命令 = 更新。
3. **检查 Xcode 路径**：Xcode 放在带空格的路径里（比如外接硬盘“My Disk”）iphone-use 会失败，这一步会自动建一个不带空格的 `/Applications/Xcode.app` 替身；然后它会打印一条 `sudo xcode-select -s …`，**你要自己复制运行并输 Mac 开机密码**。
4. **安装 iphone-use（固定 v0.19.1）**：调用 iphone-use 官方安装脚本，再跑它的设置。这一步要你动手：
   - iPhone 用数据线连上 Mac，手机上弹“要信任此电脑吗”→ 点**信任**，输锁屏密码。
   - iPhone 打开**开发者模式**：设置 → 隐私与安全性 → 开发者模式 → 打开，手机会重启，重启后再点一次“打开”。（看不到这一项的话，先在 Xcode 里连一次手机，它就会出现。）
   - Xcode → 设置 → Accounts → 左下角“+”登录你的 Apple ID。
   - 第一次装到手机后，iPhone 要去 设置 → 通用 → VPN 与设备管理 → 点你的 Apple ID → **信任**。
5. **安装向导**：见下面。

### 安装向导（8 步，之后也可以随时运行 `iphone-agent-kit init` 重来）

这个版本默认全部安装：快捷指令、后台服务、Bark 推送、直接对话规则，不再让你选“方式”。

1. **纯小白模式**（默认开）：开了以后，助手每次停下来要你动手（付款、刷脸、点信任、登录……），都会用大白话一步一步告诉你“现在要做什么、点哪里、做完怎么办”，Bark 推送也一样。
2. **选 AI 助手**（可多选，排第一个是默认）：DeepSeek Harness（`dsh`，推荐）、Claude Code、Codex。选了 Claude Code 但还没登录，会提示 `claude auth login`；检测到只有桌面版时，会问要不要帮你装命令行版（后台服务靠命令行版调用助手）。
3. **Bark**（必配）：iPhone 装好 Bark 打开，首页会显示一个网址，形如 `https://api.day.app/一串字母/…`，中间那串就是 key。把整个网址粘贴进来也行。
4. **人设“小柚”**：默认开，推送是 18 岁台湾女生的口吻（“弄好啦～”）。不喜欢就选关。
5. **外卖直接付款**：默认关，建议保持关。详见[安全提示](#安全提示)。
6. **签名到期提醒**：免费 Apple ID 签的程序 7 天过期，开了之后每天检查一次，剩 2 天时用 Bark 提醒你。
7. **生成配置和文件**：配置放在 `~/.config/iphone-agent-kit/`；会把操作手机的规则写进 `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`——**写之前会先问你**，只写在一段 `<!-- iphone-agent-kit:start -->…<!-- iphone-agent-kit:end -->` 标记里，你自己写的内容不动，改之前会备份。
8. **注册后台服务**：桥接服务开机自启，快捷指令发来的任务由它接。

装完运行一下体检，全绿就能用了：

```bash
iphone-agent-kit doctor
```

然后生成快捷指令：

```bash
iphone-agent-kit shortcuts
```

它会在桌面建一个 `iphone-agent-kit-shortcuts` 文件夹并打开。把里面的“让手机做事”**隔空投送**到你的 iPhone，点“添加快捷指令”，再设成侧边操作按钮或放到主屏幕（见上面“怎么用”）。

## 🆘 卡住了？让你电脑上的 AI 助手帮你

装不上、报错、不知道下一步，都不用自己琢磨：打开你的助手，把下面这段话原样发给它，它会自己检查、安装、修复，需要你动手的地方会一步一步告诉你怎么做。

```
我在装 iphone-agent-kit（让 AI 操控 iPhone 的工具）。请先读 https://github.com/sunxiang6789/sunxiang-ai 里的 AGENT_INSTALL.md，然后帮我：
1. 运行 iphone-agent-kit doctor 体检，看哪里不对；
2. 缺什么就帮我装，遇到要我输密码或在手机上点的，用大白话一步一步告诉我怎么做；
3. 全部正常后，告诉我下一步该做什么。
我是电脑小白，别问我技术问题，直接帮我处理。
```

特别是这几件事，**交给助手最省事**：安装助手的命令行版、给 Mac 加 `~/.local/bin` 到 PATH、处理 Xcode 路径带空格、排查 `doctor` 里的 ⚠️ 和 ❌。

## DeepSeek Harness（`dsh`，推荐）

电脑上装了 **DeepSeek Harness 桌面版**（官方，自带 `dsh` 命令行）后，向导会给 `dsh` 建一个专用配置 `iak`，接上手机工具，并**锁死**它的跑命令、读写文件、联网、子任务等能力（后台无人值守，只允许操作手机）。

- 你需要有 DeepSeek 的 **API key**：打开桌面版 → Models 页面填好。⚠️ 账号登录后桌面版自动生成的 key，命令行用不了，要自己去 platform.deepseek.com 新建一个。
- 之后在指令开头说“用 DeepSeek，……”（或“用 dsh，……”）可以临时指定它；默认助手选了它就不用说。
- 命令行版依赖官方的 MCP 插件 `@deepseek-ai/dsh-mcp-client`，向导会自动装；`dsh` 目前是候选版本（0.2.x），更新后如果不好用，重跑 `iphone-agent-kit init`。

## ⭐ 推荐使用（重点看）

我们实测了各个助手、模型的速度，**推荐用 DeepSeek Harness（`dsh`）+ 水星 3 干活，DeepSeek flash 写“收到”**。完整数据和说明见 [docs/模型与速度.md](docs/模型与速度.md)。

**命令行启动速度（⭐ 每个任务都要付的固定开销）**

| 助手（命令行） | 启动耗时（中位数） |
|---|---|
| **dsh（DeepSeek Harness）** ⭐ | **1.2～2.4 秒** |
| claude（Claude Code） | 约 6 秒 |
| codex（Codex） | 约 8.5 秒 |

**真实手机任务耗时（让它查手机还剩多少空间）**

| 模型 | 耗时 |
|---|---|
| **水星 3（dsh）** ⭐ | **约 26 秒**（热启动 13 秒） |
| Claude Sonnet 5.5 · medium | 约 41 秒 |
| Codex gpt-6.1-sol · low | 约 45 秒 |
| DeepSeek flash（dsh） | 约 53 秒 |

多步任务（看天气并记到备忘录）：水星 3 用了 40 秒，DeepSeek flash 用了 47.6 秒。

**推荐配置**

```json
{
  "default_agent": "dsh",
  "task": {
    "model": "inception/mercury-3",
    "fallbacks": [
      {"agent": "dsh", "model": "deepseek-official/deepseek-flash"},
      {"agent": "codex"},
      {"agent": "claude", "model": "claude-sonnet-5-5"}
    ]
  },
  "ack": {
    "chain": [
      {"agent": "dsh", "profile": "iak-ack", "model": "deepseek-official/deepseek-flash", "effort": "off"},
      {"agent": "claude", "model": "claude-haiku-5-5"}
    ]
  }
}
```

- **干活**：dsh + 水星 3（最快）。
- **备用**：先换 DeepSeek flash（不同服务商，一家没额度另一家还能用），再换 Codex、Claude。
- **“收到”回复**：DeepSeek flash，档位 off，约 1.2 秒。
- ⚠️ 水星 3 **不支持**档位 `off`，用水星时 `effort` 留空。
- ⚠️ 这些是 2026-10-21 在 iPhone 17 Pro 上的小样本实测，只比相对快慢；换了手机、网络、模型版本，结果会变。dsh 需要你有 DeepSeek（或水星）的 API key。

## 自己选模型、设备用模型

在 `~/.config/iphone-agent-kit/config.json` 里改，改完运行 `iphone-agent-kit restart`。完整例子见 [config.example.json](config.example.json)。

**任务用哪个助手、哪个模型，出错换谁：**

```json
{
  "default_agent": "dsh",
  "task": {
    "model": "inception/mercury-3",
    "effort": "",
    "fallbacks": [{"agent": "codex"}, {"agent": "claude", "model": "claude-sonnet-5-5"}]
  }
}
```

- `default_agent`：`claude` / `codex` / `dsh`（DeepSeek Harness）。`model`、`effort` 留空就用该助手自己的默认。
- `dsh` 的模型写成「服务商/模型」，例如 `deepseek-official/deepseek-flash`、`inception/mercury-3`；`effort` 可选 `off` / `low` / `high` / `max`。用到自己加的服务商，要先在 `~/.dsh/profiles/iak/cordis.patch.yml` 里把它配上。
- `fallbacks` 是备用，按顺序试：主用出错（没额度、key 失效、模型名不对、网络问题），或者失败得特别快（20 秒内），就自动换下一个接着做，同时推送告诉你换了谁。换的时候会提醒新助手「手机上可能已经做了一部分，别重复付款/发送」。超时和你自己叫停的不会换。

**「收到」那句回复用哪个模型：**

```json
{
  "ack": {
    "chain": [
      {"agent": "dsh", "profile": "iak-ack", "model": "deepseek-official/deepseek-flash", "effort": "off"},
      {"agent": "claude", "model": "claude-haiku-5-5"}
    ]
  }
}
```

- 按顺序试，前一个出错就换下一个；都不行就用固定的话。可以用 `dsh` / `claude` / `codex`，建议选快的：DeepSeek flash 约 1～2 秒，水星 3 约 3 秒，Claude Haiku 约 6 秒，Codex 一般超过 10 秒（不建议）。
- 回复和任务是**同时启动**的，哪怕用的不是同一个助手：你一发指令，回复那边和任务那边各自开跑，互不等待。

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

## 版本与更新

- 当前版本和每个版本改了什么：看 [Releases](https://github.com/sunxiang6789/sunxiang-ai/releases) 或 [CHANGELOG.md](CHANGELOG.md)。
- 查看自己装的版本：`iphone-agent-kit --version`（体检 `doctor` 里也会显示）。
- 更新到最新版：重新运行一遍上面的安装命令（只会更新程序，不会覆盖你的配置）。
- 想固定在某个版本：`IAK_REF=v1.0.0 bash install.sh`（或在安装命令前加 `IAK_REF=v1.0.0`）。

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
- 推荐并固定的 iphone-use 版本：**0.19.1**（作者一直在这个版本上使用）。iphone-use 更新很快，新版本是否兼容未验证，欢迎提 Issue。
- 本仓库自己的代码使用 [MIT 许可](LICENSE)。非商业项目。
