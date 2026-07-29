# Serial Terminal

PiKVM extra — 通过 USB-TTL 串口适配器在 Web UI 中提供对目标电脑的交互式命令行访问。

## Language

**Serial Terminal**:
用户在 PiKVM Web UI 中打开的终端窗口，通过串口与目标电脑交互。
_Avoid_: Serial Console, Web Terminal

**Target machine**:
被 PiKVM 远程控制的物理电脑。串口线从 PiKVM 的 USB-TTL 适配器连接到目标电脑的 COM 口。
_Avoid_: Host, remote computer, server

**Serial device**:
PiKVM 上的串口设备文件（如 `/dev/ttyUSB0`），由 USB-TTL 适配器提供。配置项 `serial.device` 的值。
_Avoid_: Serial port

**USB-TTL adapter**:
物理硬件（CH340 + MAX3232），一头插 PiKVM USB 口，一头连目标电脑 COM 口排针。

**COM port**:
目标电脑主板上的串口排针，需要在 BIOS 中开启。

### Client and access control

**Client**:
一个打开 Serial Terminal 页面的浏览器 Tab。由 `sessionStorage` 中持久化的 session ID 标识，跨页面刷新保持不变。
一个 client 有两种状态：
- **Active** — 独占串口，键盘输入转发到串口，串口输出显示在终端
- **Queued** — 全屏等待提示，不可输入也不接收输出。显示队列位置
同一时间只有一个 active client。
_Avoid_: Session, connection

**Queue**:
等待串口的 client 组成的 FIFO 队列。队首（position 1）是下一个将被提升的 client。

**Promotion**:
当 active client 释放串口时，队首的 queued client 自动变为 active 的过程。Promotion 触发一次 serial kick。

**Grace period**:
Active client 释放串口后的一段窗口期（默认 10 秒）。在此期间同一个 client 重新连接可以直接恢复 active 状态，不需排队。用于浏览器刷新场景。

**Waiting overlay**:
Queued client 看到的页面——全屏居中显示"有人正在使用串口"及队列位置（如 #1）。终端完全不渲染，直到被 promote 为 active。

**Session logout**:
最后一个 active client 断开且无排队 client 时，服务端向串口发送 `Ctrl+D`（`\x04`）终止当前 getty 会话。下一次连接的 serial kick 会触发 getty 重新打印 login 提示。

### Serial communication

**Serial kick**:
每当一个新 client 变为 active 时的初始化流程——关闭再重新打开串口（硬件尽力而为），等待稳定，发送单个 `\n` 触发目标电脑的 agetty 重新打印 login 提示符。
*注意*：CH340 + MAX3232 硬件不传递 DTR 信号，agetty 不会因此重启。`\n` kick 是唯一可靠触发 login 输出的方式。Welcome banner（`/etc/issue`）只在 agetty 真正重启时才出现。

**Relay**:
服务端后台任务——持续从串口读取数据，解码为 UTF-8 文本，通过 WebSocket 发送给 active client。每次 active client 变更时 relay 重启，确保数据发往正确 client。

### Web UI

**Canvas renderer**:
xterm.js 的 Canvas 渲染模式。使用 `<canvas>` 元素的四个渲染层（text/selection/link/cursor）替代 DOM，体感快约 10x。

**WebLinks**:
xterm.js addon——自动检测终端输出中的 URL 并使其可点击。对串口中出现的 `https://…` 地址有效。

**Search**:
xterm.js addon——`Ctrl+Shift+F` 在终端内容中搜索。长输出（`dmesg` 等）场景实用。

### Integration

**PiKVM extra**:
PiKVM 的扩展机制——通过 `manifest.yaml` 在 Web UI 菜单中注册入口，后台由独立的 systemd 服务运行。
_Avoid_: Plugin, extension, add-on
