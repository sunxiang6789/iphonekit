# 等回复工具（wait-reply）

微信里「问一句 → 等对方回 → 有结果了通知你」这类**有明确终点的长任务**，不用让大模型一直挂着等：

```
助手发出消息并登记等待任务
        │
Mac 上的 NotifWatch 读微信通知横幅（只读）──→ watch.log
        │
waiter 常驻：只有对应的群/人有回复，才调一次小模型判断「问到结果了吗」
        │ 满足 → Bark 推送结果（可选：自动叫助手接着办下一步）
        │ 不满足 → 继续等；到点 → 汇报没问到
```

等待期间**不调用模型、不碰手机**。只有被 @（横幅里没有内容）、横幅内容被「…」截断、语音（要转文字）、到点兜底检查时才接管手机，读完立刻还回去。

## 组成

| 文件 | 作用 |
|---|---|
| `notif-watch.swift` | 读 Mac「通知中心」里的微信横幅，只读，不点击；编译成 NotifWatch.app |
| `waiter.py` | 等待器：`ask`（发送并登记）、`add`（只登记）、`run`（常驻）、`list`、`rm` |
| `wx.py` | 手机微信的固定操作：读聊天列表预览、读新回复（语音长按「转文字」）、发消息（回车即发送，发完读回核对） |
| `phone.py` | 直接调 iphone-use 守护进程的 HTTP 接口，接管 → 做事 → 回主屏幕 → 交还 → 关 runner |
| `submit_task.py` | 对方回复满足条件后，把下一步作为新任务交给桥接（`--then` 用） |
| `launchd/` | 开机自启模板（waiter 和 NotifWatch） |
| `config.example.json` | 配置示例，复制成 `config.json`（已在 .gitignore 里） |

## 安装

前提：Mac 上登录了微信（用于收通知）；iPhone 通知转发到 Mac（系统设置 → 通知 → 允许来自 iPhone 的通知）；已装 iphone-use 和 iphone-agent-kit。**Mac 上装了微信时，iPhone 上的微信通知才会转到 Mac 的通知中心被读到**（实测）。

1. `sh build-notifwatch.sh` 编译并装到 `~/Applications/NotifWatch.app`。
2. 在 系统设置 → 隐私与安全性 → **辅助功能** 里给 **NotifWatch** 打开权限（脚本会提示怎么触发授权弹窗）。它是临时签名，重新编译后授权会失效，只编译一次。
3. `cp config.example.json config.json`，填你在群里被 @ 时用的昵称；判断模型的 key 用环境变量 `DEEPSEEK_API_KEY`（或 `judge.key_file`），**不要把 key 写进仓库**。
4. 启动：`open -n ~/Applications/NotifWatch.app --args --log "$PWD/watch.log"`，再 `python3 waiter.py run`。开机自启用 `launchd/` 里的模板（把 `__WAIT_REPLY_DIR__`、`__HOME__` 换成实际路径；日志写在本机 `~/Library/Logs`，不要写到外接硬盘）。

## 用法

```bash
# 发一条带 AI 标识的消息并登记等待（群聊或单聊）
python3 waiter.py ask --chat "微信里显示的名字（备注名）" --type group \
  --text "周六几点出发？" --done "有人给出了具体的出发时间" --deadline "2026-10-22 18:00" \
  [--then 'python3 submit_task.py "对方回复了：$NW_RESULT。接着去订早餐"']
python3 waiter.py list
```

- `--chat` 必须是微信聊天列表里显示的名字（有备注显示备注）。
- 同一个聊天同一时间只能有一个等待任务。
- 群里**所有人**的回复都监控；被 @ 的消息立刻推送。
- 语音回复会自动长按「转文字」读成文字；图片、视频等读不了的会推送让你自己看。
- 截止时间按 `config.json` 的 `timezone`（默认 Asia/Shanghai）理解。

### 给桥接里的助手用

桥接助手没有命令行，只能用 MCP 工具。`bridge/assistant_mcp.py` 里的 **`kit_wait_for_reply`** 工具就是它登记等待的入口：助手自己发消息，发完（还停在聊天页时）调用它；工具会核对聊天页里最后一条自己的消息确实是刚问的，防止没发就登记。启用方法：

1. 在数据目录（默认 `~/.config/iphone-agent-kit/`）新建 `waiter.json`：
   `{"waiter": "<本目录>/waiter.py", "submit": "<本目录>/submit_task.py"}`
2. 把 [`rules-snippet.md`](rules-snippet.md) 里的规则加到数据目录的 `rules.md`（同名文件优先于仓库模板）。

## 已知限制

- 读微信的方式是 macOS 通知中心的辅助功能树和微信的界面元素表，**微信或系统改界面后可能失效**。实测环境：macOS 26、微信 4.x（iOS 端）、iOS 27。
- 被 @ 时横幅只有「某某在群聊中@了你」，没有内容，所以要接管手机读。
- 聊天页里的气泡文字只有在「整屏读取」（`scope=app`）里才读得到。
- 专注模式、勿扰、Mac 微信窗口正开着该聊天时，横幅不弹，读不到；所以到点会兜底再查一次。
- 自动化操作个人微信有被平台风控的可能，量很小（每个任务一条消息）但风险仍在，请自行评估。

## 隐私

`watch.log`、`queue.jsonl`、`tasks.json`、`state.json` 里有真实的聊天内容，只在本机，**已在 .gitignore 里，不要提交或分享**。
