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

**Client**:
一个打开 Serial Terminal 页面的浏览器 Tab。由 `sessionStorage` 中持久化的 session ID 标识，跨页面刷新保持不变。
一个 client 有两种状态：
- **Active** — 独占串口，键盘输入转发到串口，串口输出显示在终端
- **Queued** — 在等待队列中，不能发送输入也不接收输出
同一时间只有一个 active client。
_Avoid_: Session, connection

**Queue**:
等待串口的 client 组成的 FIFO 队列。队首（position 1）是下一个将被提升的 client。

**Promotion**:
当 active client 释放串口时，队首的 queued client 自动变为 active 的过程。

**Grace period**:
Active client 释放串口后的一段窗口期（默认 10 秒）。在此期间同一个 client 重新连接可以直接恢复 active 状态，不需排队。用于浏览器刷新场景。

**Relay**:
服务端后台任务——持续从串口读取数据，解码为 UTF-8 文本，通过 WebSocket 发送给 active client。

**PiKVM extra**:
PiKVM 的扩展机制——通过 `manifest.yaml` 在 Web UI 菜单中注册入口，后台由独立的 systemd 服务运行。
_Avoid_: Plugin, extension, add-on
