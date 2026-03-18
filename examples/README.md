# TRex Python API Examples

These examples can run **from any machine** that can reach the TRex server
over the network (ports 4500/4501). They do NOT need to run inside the
TRex Docker container.

## Quick Start

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Run an example (uv handles all dependencies automatically)
uv run send_traffic.py --server <trex-host-ip>

# 3. Or run the full benchmark
uv run pkt_size_sweep.py --server <trex-host-ip>
```

That's it. No virtualenv, no pip install, no Docker needed on the client side.

## How It Works

Each script uses a `/// script` metadata header that tells `uv` what
dependencies to install (just `pyzmq` and `scapy`). On first run, `uv`
creates a cached virtual environment automatically.

The TRex Python API files are included in `trex_client/` (copied from
the TRex source tree). They use the system `pyzmq` package instead of
TRex's bundled `pyzmq-ctypes`.

## Examples

| Script | Description |
|--------|-------------|
| `send_traffic.py` | Simple 1 Mpps UDP test on port 0 |
| `pkt_size_sweep.py` | Full packet size sweep (64-1518B) at max rate |

## Prerequisites

- TRex server running (see main README)
- Network connectivity to TRex host on ports 4500, 4501
- `uv` installed (or Python 3.8+ with `pip install pyzmq scapy`)
