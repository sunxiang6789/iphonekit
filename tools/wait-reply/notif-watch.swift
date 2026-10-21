// notif-watch: 原型。轮询 macOS 通知中心进程的辅助功能树，打印新出现的通知横幅文字。
// 用法：
//   notif-watch            监听并打印新横幅（每条一行 JSON）
//   notif-watch --dump     打印一次通知中心当前的整棵 AX 树（调试结构用）
//   notif-watch --check    只检查辅助功能权限和通知中心进程
// 只读，不点击、不发送任何东西。
import AppKit
import ApplicationServices
import Foundation

let bundleID = "com.apple.notificationcenterui"

func attr(_ el: AXUIElement, _ name: String) -> AnyObject? {
    var v: CFTypeRef?
    guard AXUIElementCopyAttributeValue(el, name as CFString, &v) == .success else { return nil }
    return v as AnyObject?
}

func str(_ el: AXUIElement, _ name: String) -> String? {
    if let s = attr(el, name) as? String, !s.isEmpty { return s }
    return nil
}

func children(_ el: AXUIElement) -> [AXUIElement] {
    (attr(el, kAXChildrenAttribute) as? [AXUIElement]) ?? []
}

func ncApp() -> AXUIElement? {
    guard let app = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first else { return nil }
    return AXUIElementCreateApplication(app.processIdentifier)
}

func dump(_ el: AXUIElement, _ depth: Int) {
    let role = str(el, kAXRoleAttribute) ?? "?"
    var parts = [String(repeating: "  ", count: depth) + role]
    for (label, key) in [("sub", kAXSubroleAttribute), ("title", kAXTitleAttribute), ("value", kAXValueAttribute),
                         ("desc", kAXDescriptionAttribute), ("id", kAXIdentifierAttribute)] {
        if let s = str(el, key) { parts.append("\(label)=\(s.replacingOccurrences(of: "\n", with: "\\n"))") }
    }
    print(parts.joined(separator: " "))
    for c in children(el) { dump(c, depth + 1) }
}

/// 收集一棵子树里所有有文字的节点（标题、值、描述），保持出现顺序，去重。
func texts(_ el: AXUIElement, _ out: inout [String]) {
    let role = str(el, kAXRoleAttribute) ?? ""
    if role == "AXStaticText" || role == "AXButton" || role == "AXGroup" {
        for key in [kAXValueAttribute, kAXTitleAttribute, kAXDescriptionAttribute] {
            if let s = str(el, key), !out.contains(s) { out.append(s) }
        }
    }
    for c in children(el) { texts(c, &out) }
}

func banners(_ app: AXUIElement) -> [[String]] {
    var result: [[String]] = []
    for w in (attr(app, kAXWindowsAttribute) as? [AXUIElement]) ?? [] {
        var t: [String] = []
        texts(w, &t)
        if !t.isEmpty { result.append(t) }
    }
    return result
}

func emit(_ obj: [String: Any]) {
    if let d = try? JSONSerialization.data(withJSONObject: obj, options: [.withoutEscapingSlashes]),
       let s = String(data: d, encoding: .utf8) { print(s); fflush(stdout) }
}

// 作为 App 启动时没有终端：--log <文件> 把 stdout/stderr 都写到该文件
let rawArgs = CommandLine.arguments
if let i = rawArgs.firstIndex(of: "--log"), i + 1 < rawArgs.count {
    freopen(rawArgs[i + 1], "a", stdout)
    freopen(rawArgs[i + 1], "a", stderr)
    setvbuf(stdout, nil, _IOLBF, 0)
}
let args = CommandLine.arguments.dropFirst()
let prompt = args.contains("--prompt")
let trusted = prompt
    ? AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary)
    : AXIsProcessTrusted()

if args.contains("--check") {
    emit(["accessibility_trusted": trusted,
          "notification_center_running": ncApp() != nil])
    exit(trusted ? 0 : 2)
}

guard trusted else {
    FileHandle.standardError.write(Data("没有辅助功能权限：系统设置 → 隐私与安全性 → 辅助功能，给运行本程序的应用打开。\n".utf8))
    exit(2)
}
guard let app = ncApp() else {
    FileHandle.standardError.write(Data("找不到通知中心进程\n".utf8))
    exit(3)
}

if args.contains("--dump") {
    dump(app, 0)
    exit(0)
}

var lastKeys = Set<String>()
while true {
    let current = banners(ncApp() ?? app)
    var keys = Set<String>()
    for b in current {
        let key = b.joined(separator: "|")
        keys.insert(key)
        // 同一条横幅停留期间只报一次；消失后再出现同样文字算新的
        if !lastKeys.contains(key) {
            emit(["ts": Int(Date().timeIntervalSince1970), "texts": b])
        }
    }
    lastKeys = keys
    Thread.sleep(forTimeInterval: 0.4)
}
