# 给 AI 助手的安装指南（助手读这一页，用户不用看）

你（Claude Code / Codex / DeepSeek Harness 的命令行助手）正在帮一位**电脑小白**安装 iphone-agent-kit。
目标：装好之后，用户按下 iPhone 侧边按钮（或点主屏幕上的快捷指令）说一句话，Mac 上的助手就去操作手机，办完用 Bark 推送结果。

**和用户说话的规则**
- 用简体中文、大白话，别甩术语和报错原文。需要用户动手的地方，**一步一步**说：点哪里、看到什么、做完告诉你。
- 一次只让用户做一件事，等他回复再继续。
- 能自己做的自己做，不要问用户技术问题。

## 铁律（先读完再动手）

1. **不要读或打印**密码、令牌、API key、Bark key、`~/.dsh/.credentials.yaml`、iphone-use 的密码文件。用户把 key 发给你时，只用来写配置，不要在回复里复述。
2. **不要替用户输 Mac 密码**，也不要自己加 `sudo` 偷偷执行。需要 `sudo` 的命令，把整条命令给用户，让他自己在终端里粘贴运行并输密码。
3. **不要改 iphone-use 本体的文件**；不要运行 `iphone-use update`（会换版本）。
4. **iphone-use 固定用 0.19.1**（本工具实测的版本）。装机时由 `install.sh` 自动固定；用户已经装了别的版本且在正常使用时，**先问用户**「要换成推荐的 0.19.1，还是保持现在这个？」，不要擅自降级。
5. 测试手机时：**不付款、不给真人发消息**；发消息测试只发「文件传输助手」；备忘录测试只建标题带「【测试】」的新笔记，测完只删自己建的那条。
6. 写入 `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` 之前，**必须先问用户**「要把操作手机的规则（付款由你自己付等）写进这个文件吗？只写在一段标记里，其他内容不动，改之前会备份」，同意后再写。
7. 付款、转账、购买等需要用户本人确认的事，永远只做到付款页就停，由用户自己点。

## 第 0 步：先了解现状（只读，不改任何东西）

```bash
sw_vers -productVersion; uname -m; python3 --version
xcode-select -p; ls -d /Applications/Xcode*.app "/Volumes/"*/Xcode*.app 2>/dev/null
command -v iphone-use iphone-agent-kit claude codex dsh
iphone-use --version 2>/dev/null
iphone-agent-kit doctor 2>/dev/null
```

据此告诉用户：「我看了一下，你的电脑还缺 X、Y，我来处理，中间有几处要你动手」。

## 第 1 步：问清三件事（一次问完）

1. 「你用哪个 AI 助手来操控手机？**推荐 DeepSeek Harness 的命令行 dsh**（最快，1～2 秒启动）；也可以 Claude Code 或 Codex。」
   - 选 dsh：需要先装 **DeepSeek Harness 桌面版**（官方），并在它的 **Models 页面保存好 API key**。注意：账号登录后桌面版自动生成的 key 命令行用不了，要去 platform.deepseek.com 自己新建一个再填进去。你只需要让用户确认「已经在 Models 页面保存好 key」，**不要去读 key**。
2. 「推送要用一个免费的 **Bark** App。手机连上电脑之后，我来帮你在 App Store 里找到它，你只需要点一下“获取”并刷脸或输 Apple ID 密码。如果你已经装过 Bark，告诉我。」
3. 「你的 iPhone 是哪个型号？」15 Pro 及以上有**操作按钮**，可以设成一按就说话；其他机型把快捷指令放主屏幕。

## 第 2 步：运行安装

```bash
curl -fsSL https://raw.githubusercontent.com/sunxiang6789/sunxiang-ai/main/install.sh | bash -s -- --no-init
```

它会：检查环境 → 装程序文件 → 处理 Xcode 路径空格 → **固定安装 iphone-use v0.19.1** → 跑 iphone-use setup（这一步要用户动手，见第 3 步）。`--no-init` 表示先不进向导，因为你在非交互终端里没法回答向导的提问。

装完后先别运行向导：要先做第 3～5 步（手动操作、版本确认、装 Bark 拿 key），再到第 6 步跑向导。

## 第 3 步：必须交给用户动手的事（逐条念给他，做完再下一条）

| 什么时候 | 对用户说什么 |
|---|---|
| Xcode 路径有空格 | 「请复制下面这一整行，粘贴到终端按回车，然后输入你的 Mac 开机密码（输入时屏幕不显示，正常的）：`sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`」 |
| 没有完整 Xcode | 「请到 App Store 搜 Xcode 安装（十几 G），装好后打开一次，同意协议，再告诉我。」 |
| 手机连接 | 「请用数据线把 iPhone 连到 Mac，手机解锁。手机上弹出『要信任此电脑吗』，点**信任**，输入锁屏密码。」 |
| 开发者模式 | 「iPhone 打开：设置 → 隐私与安全性 → 开发者模式 → 打开。手机会重启，重启后会再弹一次，点『打开』。」（看不到这一项：先在 Xcode 里连一次手机它就会出现） |
| Apple ID | 「Mac 上打开 Xcode → 设置 → Accounts → 左下角『+』，登录你的 Apple ID（免费的就行）。」 |
| 第一次装到手机后 | 「iPhone 上：设置 → 通用 → VPN 与设备管理 → 点你的 Apple ID → 信任。」 |
| 手机要保持 | 「安装期间手机保持亮屏、解锁，别锁屏。」 |
| 快捷指令 | 见第 7 步 |

任何一步失败：看 `iphone-agent-kit doctor` 的提示，一条一条修；修不了，把原因用大白话告诉用户，不要硬试。

## 第 4 步：确认 iphone-use 版本

```bash
iphone-use --version
```

应该是 0.19.1。不是的话，按铁律 4 先问用户。需要手动固定安装时：

```bash
curl -fsSL https://raw.githubusercontent.com/leeguooooo/iphone-use/v0.19.1/install.sh | IPHONE_USE_RELEASE_REF=v0.19.1 sh
```

## 第 5 步：帮用户装 Bark，并拿到推送地址（严防装错）

前提：第 3、4 步已完成，手机已经能被操控（`iphone-agent-kit doctor` 里 iphone-use 正常）。用户说已经装过 Bark 的，跳到本节第 5 点。

**要装的是这一个，必须逐项核对，对不上就不要点“获取”：**

| 项目 | 正确的 Bark |
|---|---|
| 中文名 | **Bark - 给你的手机发推送**（英文区叫 *Bark - Custom Notifications*） |
| 开发者 | **丰 黄**（英文常写作 Finb / Fin） |
| 包名（bundle id） | **me.fin.bark** |
| App Store 编号 | **1403753865** |
| 图标 | **红色背景，中间一个白色的“蝴蝶结/骨头”形图案**（左右两个梯形，中间一个长方块）。图片见 [docs/assets/bark-icon.jpg](docs/assets/bark-icon.jpg)，先自己看一眼再动手 |
| 价格 | 免费 |
| 开源仓库 | [github.com/Finb/Bark](https://github.com/Finb/Bark)（MIT 许可），作者 Finb，README 里的 App Store 链接指向同一个编号 1403753865，可作为第二个核对依据 |

⚠️ **名字相近的是别的 App，千万不要装**：
- “全能消息推送Bark”（Foshan Qizhizhu Technology 开发）
- “Bark - Effortless and Cute Way to Chat”（DongHyeok Kim 开发，绿色系，不是推送工具）
- “Bravo - 给你的手机发推送”（Xiwan 开发）
- 任何开发者不是“丰 黄”的“Bark”。
- 也**不要**从 GitHub 或其他网站下载 `.ipa` 来侧载 Bark：App Store 官方版才稳定（不会 7 天过期），来路不明的包不装。

做法：

1. **直接用链接打开，不要在 App Store 里搜索**（搜索结果里有一堆同名的，容易点错）。让手机打开：`https://apps.apple.com/app/id1403753865`（会跳到 App Store 的正确页面）。用你的手机控制工具（比如 iphone-use 的打开链接，或在 Safari 地址栏输入这个链接）。
2. **读屏幕核对**：App 名称、开发者“丰 黄”、红色图标这三样都对得上，才继续；否则停下，告诉用户“页面不对”，不要点任何按钮。
3. **只让用户自己点“获取”**，并告诉他：「请点右边的‘获取’，然后按提示刷脸或输 Apple ID 密码。」**你不要点“获取”或“安装”，也不要替用户输 Apple ID 密码。** 如果手机没登录 Apple ID，让用户自己在 设置 里登录。
4. 等用户说装好了，再核对：用 `phone_apps`（`source: installed`）查已安装列表，里面必须有包名 **me.fin.bark**。**没有、或只有别的 Bark，就是装错了**：告诉用户，**不要擅自删除**，问他要不要删掉装错的那个，再重来。
5. 用包名 `me.fin.bark` 打开 Bark。第一次打开会弹“是否允许通知”：**让用户自己点“允许”**（不允许就收不到推送）。
6. Bark 首页会显示一个网址，形如 `https://api.day.app/一串字母/内容`。**中间那串字母就是推送 key**，读屏幕取到它，只用于第 6 步的 `--bark-key`。**key 是秘密：不要在回复里复述，不要写进日志或其他文件。** 页面上如果列了多个服务器，选默认的 `api.day.app` 那个。
7. 这里只需确认 key 取到了；真正的测试推送在第 6 步向导里发。

失败时（页面打不开、布局变了、读不到网址）：退回手动方式——让用户自己去 App Store 搜“Bark”（认准上面的开发者“丰 黄”和红色图标），装好后把首页网址发给你。

## 第 6 步：运行向导（无人值守）

```bash
iphone-agent-kit init --yes --beginner on --agent dsh --bark-key "<上一步拿到的 key 或网址>"
```

`--agent` 可选 `dsh` / `claude` / `codex` / `both`（claude+codex）/ `all`（三个都用）。第一个是默认。其余选项保持默认（人设开、外卖直接付款关、签名到期提醒按是否配了 Bark）。向导会发一条测试推送，让用户确认手机收到了。

## 第 7 步：快捷指令（主推用法）

```bash
iphone-agent-kit shortcuts
```

会在桌面生成 `iphone-agent-kit-shortcuts` 文件夹。然后带用户做：

1. 「把里面的『让手机做事』用**隔空投送**发到你的 iPhone，手机上点『添加快捷指令』。」
2. **设成侧边按钮（主推，iPhone 15 Pro 及以上）**：「设置 → 操作按钮 → 往右滑到『快捷指令』→ 选择『让手机做事』。」以后按住侧边操作按钮就开始说话。
3. 其他机型：「长按快捷指令 → 分享 → 添加到主屏幕」，点图标说话；也可以对 Siri 说「让手机做事」。

## 第 8 步：验收（每项都要做）

1. `iphone-agent-kit doctor`：除了无关紧要的 ⚠️，不应该有 ❌。
2. 让用户按侧边按钮（或点图标）说：**「现在几点了」**。应在 1～2 秒内收到一条 Bark 推送，手机屏幕不动。没收到：查 Bark key（`doctor`）和 `iphone-agent-kit logs`。
3. 再让用户说一个无害的手机任务：**「看看手机还剩多少空间」**。会先收到一条「收到」，十几到几十秒后收到结果推送。
4. 如果用户锁了屏，应收到「需要解锁」的推送；解锁后再按一次按钮说「解锁了」，会接着做。
5. 全部通过后，告诉用户：
   - 一句话怎么用（按钮 → 说话 → 等推送）。
   - 说「停止」可以叫停；说「新任务：……」另起一件事。
   - **免费 Apple ID 签的手机端程序 7 天过期**，到期前会推送提醒，到时在 Mac 终端运行 `iphone-agent-kit resign`。
   - 个人档案在 `~/.config/iphone-agent-kit/profile.md`，口味、地址写进去，助手做选择时会读。

## 收尾

- 用完手机后按规则：回主屏幕 → 交还手机 → 关 runner（桥接服务会自动做）。
- 用 `iphone-agent-kit doctor` 的最终结果和下一步建议，向用户做一个简短总结。
