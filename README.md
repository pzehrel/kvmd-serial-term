# PiKVM Serial Terminal

[English](README.en.md)

PiKVM 扩展——通过 USB-TTL 串口适配器在 Web UI 中对目标电脑进行交互式命令行访问，无需 HDMI 显示器。

```
┌─────────────┐     USB-TTL      ┌──────────────────┐
│   PiKVM     │  (CH340+MAX3232) │   目标电脑         │
│             │◄════════════════►│   (e.g. Proxmox)  │
│  Web UI     │   Serial COM     │   Serial Console   │
│   xterm.js  │                  │                    │
└─────────────┘                  └──────────────────┘
```

## 功能

- 在 PiKVM Web UI 中提供完整的 xterm.js 终端体验
- 支持 Canvas / DOM 双渲染模式
- 自动检测终端输出中的 URL 并使其可点击（WebLinks）
- `Ctrl+Shift+F` 终端内搜索（Search）
- 浏览器刷新 10 秒内自动恢复连接
- 多客户端自动排队：先到先得，队首自动提升
- 关闭页面自动注销 getty 会话，下次打开显示完整 welcome banner
- 串口参数可配置（波特率、校验位等）
- 标准 PiKVM extra 部署：systemd 守护 + manifest 注册

## 硬件要求

- USB-TTL 适配器：CH340（或同类）+ MAX3232 用于 RS-232 电平转换
- 目标电脑主板 COM 口排针

> **接线说明请参阅 [docs/hardware/wiring.md](docs/hardware/wiring.md)**

## 目标电脑配置

1. **BIOS 中开启 COM 口**——通常在 "Super IO" 或 "Peripherals" 菜单下
2. **配置串口 console**：

   **Proxmox VE / Debian / Ubuntu:**
   ```
   # 编辑 /etc/default/grub
   GRUB_CMDLINE_LINUX="console=ttyS0,115200n8"

   # 更新并重启
   update-grub
   reboot
   ```

   **通用 Linux:**
   在内核命令行中添加 `console=ttyS0,115200n8`

3. **连接适配器：**

   参见 [接线说明](docs/hardware/wiring.md)

## 安装

在 PiKVM 上：

```bash
# 1. 克隆仓库
git clone https://github.com/pzehrel/kvmd-serial-term.git /opt/kvmd-serial-term
cd /opt/kvmd-serial-term

# 2. 执行一键部署
bash deploy.sh
```

`deploy.sh` 会自动完成：Python 包安装、配置文件创建、systemd 服务注册、PiKVM extra 注册、Nginx 集成。

## 配置

`/etc/kvmd/serial-term.yaml`：

```yaml
serial:
  device: /dev/ttyUSB0      # 串口设备路径
  baudrate: 115200          # 波特率：300–921600
  bytesize: 8               # 数据位：5, 6, 7, 8
  parity: N                 # 校验：N, E, O, M, S
  stopbits: 1               # 停止位：1, 1.5, 2
  xonxoff: false            # 软件流控
  rtscts: false             # 硬件流控

server:
  unix_socket: /run/kvmd/serial-term.sock
  web_dir: /usr/share/kvmd/web/serial-term
```

所有串口字段均可选——默认值为 `115200-8-N-1`。

## 使用

1. 打开 PiKVM Web UI
2. 在导航菜单中点击 **Serial Terminal**（排在内置 Terminal 前面）
3. 终端窗口打开——输入用户名密码登录目标电脑
4. 同一时间只有一个用户控制串口；其他用户看到全屏排队提示
5. 关闭页面后自动注销 shell，下次打开显示完整 welcome banner

## 开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest tests/ -v
```

## 许可

GPL-3.0
