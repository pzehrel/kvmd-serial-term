# CH340 + MAX3232 → Motherboard COM Port Wiring

> [中文](wiring.zh.md)

## Required Hardware

| Component | Purpose |
|-----------|---------|
| CH340 USB-TTL module | USB to TTL serial (3.3V/5V logic level) |
| MAX3232 module | TTL ↔ RS-232 level shifting (±3V~±15V) |
| 3× Dupont wires | TX, RX, GND |

## Motherboard COM Port Header Pinout

The COM header is on the bottom-left of the motherboard, labeled **COM**, standard 9-pin layout.

**Pin 1 is on the right. Pins increment alternating top/bottom** (right→left: 1→2→3→…→9):

| | | | | | |
| :---: | :---: | :---: | :---: | :---: | :---: |
| Top row | 9<br/>NRI- | 7<br/>NRTS- | **5<br/>GND** | **3<br/>NSOUT** | 1<br/>NDCD- |
| Bottom row | (NC) | 8<br/>NCTS- | 6<br/>NDSR- | 4<br/>NDTR- | **2<br/>NSIN** |

**Essential pins:**

| Pin | Signal | Direction | Description |
|-----|--------|-----------|-------------|
| Pin 2 | NSIN | MB ← external | Motherboard serial receive (RX) |
| Pin 3 | NSOUT | MB → external | Motherboard serial transmit (TX) |
| Pin 5 | GND | — | Common ground |

## Wiring Diagram

> **Important**: Both the TTL side and RS232 side of the MAX3232 use a **cross-over connection** — TX of one end goes to RX of the other.

```
┌─────────┐                  ┌───────────┐                  ┌──────────────┐
│  CH340  │                  │  MAX3232  │                  │    MB COM     │
│         │                  │           │                  │              │
│  TXD ───┼──────────────────┼→ RXD(TTL) │                  │              │
│         │                  │           │                  │              │
│  RXD ───┼──────────────────┼─ TXD(TTL) │                  │              │
│         │                  │           │                  │              │
│  VCC ───┼──────────────────┼→ VCC      │                  │              │
│         │                  │           │                  │              │
│  GND ───┼────────┬─────────┼→ GND      │                  │              │
│         │        │         │           │                  │              │
│         │        │   TTL   │  RS232    │                  │              │
│         │        │         │  TX ──────┼──────────────────┼→ Pin 2 (NSIN) │
│         │        │         │           │                  │              │
│         │        │         │  RX ──────┼──────────────────┼─ Pin 3 (NSOUT)│
│         │        │         │           │                  │              │
│         │        └─────────┼─ GND ─────┼──────────────────┼→ Pin 5 (GND)  │
│         │                  │           │                  │              │
└─────────┘                  └───────────┘                  └──────────────┘
```

| Signal | CH340 | MAX3232 (TTL) | MAX3232 (RS232) | COM Header |
|--------|-------|---------------|-----------------|------------|
| Transmit | TXD | RXD | TX | Pin 2 (NSIN) |
| Receive | RXD | TXD | RX | Pin 3 (NSOUT) |
| Power | VCC | VCC | — | — |
| Ground | GND | GND | GND | Pin 5 (GND) |

## Signal Flow

```
Keyboard → PiKVM → CH340(TXD) → MAX3232(TTL→RS232) → COM Pin 2(NSIN) → PVE shell
PVE shell → COM Pin 3(NSOUT) → MAX3232(RS232→TTL) → CH340(RXD) → PiKVM → Browser
```

## Serial Parameters

| Parameter | Value |
|-----------|-------|
| Baud rate | 115200 |
| Data bits | 8 |
| Stop bits | 1 |
| Parity | None |
| Flow control | None |

The PVE-side agetty auto-adapts to `115200,57600,38400,9600` (`--keep-baud`).

## FAQ

### Garbled output

Check that the GND wire is connected — without a common ground reference the UART cannot distinguish signal from noise. If GND is connected, try re-plugging the USB-TTL adapter.

### Blank terminal

Confirm the TX/RX wires on the COM header are crossed (TX of one end → RX of the other). TX-to-TX and RX-to-RX means both sides transmit but neither receives.

### Cannot type

Check that `serial-getty@ttyS0` is enabled on PVE:

```bash
systemctl status serial-getty@ttyS0
```

If it shows `inactive`:

```bash
systemctl enable --now serial-getty@ttyS0
```
