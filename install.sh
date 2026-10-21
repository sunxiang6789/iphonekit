#!/usr/bin/env bash
# iphone-agent-kit 一键安装（Mac + iPhone）。
#   curl -fsSL https://raw.githubusercontent.com/sunxiang6789/sunxiang-ai/main/install.sh | bash
# 重复运行 = 更新到最新版并重新跑向导。
#
# 可用选项（curl … | bash -s -- --dry-run）：
#   --dry-run   只打印会做什么，不改任何东西
#   --yes       向导的所有提问用默认值
#   --skip-iphone-use   不装 / 不 setup iphone-use（已经装好时）
#   --no-init   装完程序就停，不跑向导
# 环境变量：IAK_REPO_URL（仓库地址）、IAK_REF（分支或标签，默认 main）、IAK_IPHONE_USE_VERSION（默认 v0.19.1）
set -euo pipefail

NAME="iphone-agent-kit"
REPO_URL="${IAK_REPO_URL:-https://github.com/sunxiang6789/sunxiang-ai.git}"
REF="${IAK_REF:-main}"
INSTALL_DIR="$HOME/.local/share/$NAME"
BIN_DIR="$HOME/.local/bin"
# 本工具实测的 iphone-use 版本；新版本不保证兼容，所以固定装这个（IAK_IPHONE_USE_VERSION 可改，不建议）。
IPHONE_USE_VERSION="${IAK_IPHONE_USE_VERSION:-v0.19.1}"
IPHONE_USE_INSTALLER="https://raw.githubusercontent.com/leeguooooo/iphone-use/$IPHONE_USE_VERSION/install.sh"

DRY=0; YES=0; SKIP_IU=0; NO_INIT=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --yes) YES=1 ;;
    --skip-iphone-use) SKIP_IU=1 ;;
    --no-init) NO_INIT=1 ;;
    *) echo "不认识的选项：$arg"; exit 2 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
ok()   { printf '  ✅ %s\n' "$*"; }
warn() { printf '  ⚠️  %s\n' "$*"; }
die()  { printf '  ❌ %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then say "  [试运行] $*"; else "$@"; fi; }

say "=== $NAME 安装 ==="
if [ "$DRY" = 1 ]; then say "（试运行：只打印，不改任何东西）"; fi

# ---------------------------------------------------------------- 1 环境检查
say ""; say "【1/5】检查环境"
[ "$(uname -s)" = "Darwin" ] || die "只支持 macOS（iphone-use 需要 Xcode，Windows / Linux 不行）"
ok "macOS $(sw_vers -productVersion 2>/dev/null || echo '?')，$(uname -m)"

command -v python3 >/dev/null 2>&1 || die "找不到 python3。请先在终端运行：xcode-select --install ，装完重跑本脚本"
ok "$(python3 --version 2>&1)"

TZ_NAME=""
if [ -L /etc/localtime ]; then TZ_NAME="$(readlink /etc/localtime | sed 's|.*zoneinfo/||')"; fi
[ -n "$TZ_NAME" ] || TZ_NAME="${TZ:-UTC}"
ok "系统时区 $TZ_NAME（之后跑 iphone-use 会自动带上，避免进程校验失败）"

DEV_DIR="$(xcode-select -p 2>/dev/null || true)"
if [ -z "$DEV_DIR" ]; then
  warn "没找到 Xcode。iphone-use 需要完整的 Xcode（不是只有命令行工具）：从 App Store 装好，打开一次同意协议，再重跑本脚本"
  [ "$DRY" = 1 ] || die "缺 Xcode"
else
  ok "Xcode 开发目录 $DEV_DIR"
fi

if ! command -v git >/dev/null 2>&1 && ! command -v curl >/dev/null 2>&1; then die "需要 git 或 curl"; fi
command -v curl >/dev/null 2>&1 || die "需要 curl"

# ---------------------------------------------------------------- 2 取得程序文件
say ""; say "【2/5】安装程序文件到 $INSTALL_DIR"
SELF_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$SELF_DIR" ] && [ -f "$SELF_DIR/bin/$NAME" ]; then
  KIT_DIR="$SELF_DIR"
  ok "从本地目录安装（不下载）：$KIT_DIR"
else
  KIT_DIR="$INSTALL_DIR"
  case "$REPO_URL" in *"<账号>"*) die "仓库地址还是占位符，请设置 IAK_REPO_URL" ;; esac
  if [ -d "$INSTALL_DIR/.git" ]; then
    run git -C "$INSTALL_DIR" fetch --depth 1 origin "$REF"
    run git -C "$INSTALL_DIR" checkout -q FETCH_HEAD
    ok "已更新"
  elif command -v git >/dev/null 2>&1; then
    run mkdir -p "$(dirname "$INSTALL_DIR")"
    run git clone --depth 1 --branch "$REF" "$REPO_URL" "$INSTALL_DIR"
    ok "已下载"
  else
    run mkdir -p "$INSTALL_DIR"
    if [ "$DRY" = 1 ]; then say "  [试运行] 下载 ${REPO_URL%.git}/archive/$REF.tar.gz 并解压到 $INSTALL_DIR"
    else curl -fsSL "${REPO_URL%.git}/archive/$REF.tar.gz" | tar -xz --strip-components=1 -C "$INSTALL_DIR"; fi
    ok "已下载"
  fi
fi

run mkdir -p "$BIN_DIR"
run ln -sfn "$KIT_DIR/bin/$NAME" "$BIN_DIR/$NAME"
run chmod +x "$KIT_DIR/bin/$NAME"
ok "命令已放到 $BIN_DIR/$NAME"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR 还不在你的 PATH 里。运行下面这行，并把它加到 ~/.zshrc："
     say "     export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac
export PATH="$BIN_DIR:/opt/homebrew/bin:/usr/local/bin:$HOME/.iphone-use/bin:$PATH"
KIT="$KIT_DIR/bin/$NAME"

# ---------------------------------------------------------------- 3 Xcode 路径
say ""; say "【3/5】检查 Xcode 路径（路径里有空格 iphone-use 会失败）"
if [ "$DRY" = 1 ]; then say "  [试运行] python3 $KIT fix-xcode"
else python3 "$KIT" fix-xcode || warn "上面的 Xcode 问题处理完后，重跑本脚本"; fi

# ---------------------------------------------------------------- 4 iphone-use
say ""; say "【4/5】iphone-use（本工具基于它，由 leeguooooo 开发，PolyForm Shield 许可，这里只调用它官方的安装脚本）"
if [ "$SKIP_IU" = 1 ]; then
  say "  已跳过（--skip-iphone-use）"
else
  if command -v iphone-use >/dev/null 2>&1; then
    HAVE_IU="$(iphone-use --version 2>/dev/null | head -1 || true)"
    ok "已装 iphone-use：$(command -v iphone-use)（${HAVE_IU:-版本未知}）"
    case "$HAVE_IU" in
      *"${IPHONE_USE_VERSION#v}"*) ;;
      *) warn "本工具实测的是 iphone-use $IPHONE_USE_VERSION，你装的版本不同，可能不兼容。不会自动降级正在用的版本；想换的话，让助手照 AGENT_INSTALL.md 处理。" ;;
    esac
  else
    say "  固定安装实测过的版本 $IPHONE_USE_VERSION：$IPHONE_USE_INSTALLER"
    if [ "$DRY" = 1 ]; then say "  [试运行] curl -fsSL $IPHONE_USE_INSTALLER | IPHONE_USE_RELEASE_REF=$IPHONE_USE_VERSION sh"
    else curl -fsSL "$IPHONE_USE_INSTALLER" | IPHONE_USE_RELEASE_REF="$IPHONE_USE_VERSION" sh || die "iphone-use 安装失败，请看上面的报错"; fi
  fi
  say "  接下来运行 iphone-use setup（TZ=$TZ_NAME）。过程中请把 iPhone 用数据线连上 Mac、解锁、点「信任」，"
  say "  并在 Xcode 里登录你的 Apple ID；手机上要打开「开发者模式」。按它的提示一步步来。"
  if [ "$DRY" = 1 ]; then say "  [试运行] TZ=$TZ_NAME iphone-use setup"
  else python3 "$KIT" iu setup || warn "iphone-use setup 没成功。处理完问题后运行：iphone-agent-kit iu setup"; fi
fi

# ---------------------------------------------------------------- 5 向导
say ""; say "【5/5】安装向导"
if [ "$NO_INIT" = 1 ]; then
  say "  已跳过（--no-init）。之后运行：$NAME init"
else
  INIT_ARGS=()
  [ "$DRY" = 1 ] && INIT_ARGS+=(--dry-run)
  [ "$YES" = 1 ] && INIT_ARGS+=(--yes)
  if [ "$YES" = 1 ] || { : </dev/tty; } 2>/dev/null; then
    if [ "$YES" = 1 ]; then python3 "$KIT" init ${INIT_ARGS[@]+"${INIT_ARGS[@]}"}
    else python3 "$KIT" init ${INIT_ARGS[@]+"${INIT_ARGS[@]}"} </dev/tty; fi
  else
    warn "当前不是交互终端，向导没法提问。请在终端里运行：$NAME init"
  fi
fi

say ""
say "=== 安装结束 ==="
say "常用命令：$NAME doctor | shortcuts | resign | status | restart | logs | uninstall"
