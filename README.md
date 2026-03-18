# TRex ARM64 (aarch64) - DGX Spark Edition

TRex v3.08 traffic generator ported to ARM64, targeting NVIDIA DGX Spark
with ConnectX-7 NICs. Built from the official
[cisco-system-traffic-generator/trex-core](https://github.com/cisco-system-traffic-generator/trex-core)
with patches for aarch64 compilation and runtime compatibility.

> The original upstream README is preserved in [README_OLD.asciidoc](README_OLD.asciidoc).

## Quick Start

### Build

```bash
docker build -t trex-arm64:latest .
```

Build time is ~2 minutes on DGX Spark (20 ARM cores). The Dockerfile is a
multi-stage build that uses system `libibverbs-dev`, `libzmq3-dev`, and
`libmnl-dev` from Ubuntu 24.04 for the aarch64 libraries that upstream
TRex only bundles for x86_64.

### Run (Stateless Server)

```bash
docker run -d --rm --privileged --net=host \
    --name trex \
    -v /dev:/dev \
    -v /sys:/sys \
    -v /path/to/trex_cfg.yaml:/etc/trex_cfg.yaml:ro \
    --entrypoint bash \
    trex-arm64:latest \
    -c 'cd /opt/trex/scripts && ./t-rex-64 -i --stl --cfg /etc/trex_cfg.yaml --no-scapy-server --iom 0'
```

If the `t-rex-64` wrapper fails (see Troubleshooting), use the binary
directly with `--mlx5-so`:

```bash
    -c 'cd /opt/trex/scripts && ./_t-rex-64 -i --stl --cfg /etc/trex_cfg.yaml --no-scapy-server --mlx5-so --iom 0'
```

### Run (Interactive / Single Test)

```bash
docker run --rm -it --privileged --net=host \
    -v /dev:/dev \
    -v /sys:/sys \
    -v /path/to/trex_cfg.yaml:/etc/trex_cfg.yaml:ro \
    --entrypoint bash \
    trex-arm64:latest \
    -c 'cd /opt/trex/scripts && ./_t-rex-64 -i --cfg /etc/trex_cfg.yaml --no-scapy-server --mlx5-so'
```

## Configuration

Example `trex_cfg.yaml` for DGX Spark with ConnectX-7 (dual PCIe domain):

```yaml
- port_limit: 2
  version: 2
  interfaces: ["0000:01:00.0", "0002:01:00.0"]
  port_info:
    - dest_mac: "30:c5:99:3f:be:8c"   # remote port 0 MAC
      src_mac:  "30:c5:99:3f:96:b7"   # local port 0 MAC
    - dest_mac: "30:c5:99:3f:be:90"   # remote port 1 MAC
      src_mac:  "30:c5:99:3f:96:bb"   # local port 1 MAC
  platform:
    master_thread_id: 0
    latency_thread_id: 10
    dual_if:
      - socket: 0
        threads: [1, 2, 3, 4, 5, 6, 7, 8, 9]
  c: 9
  new_memory: true
  port_mtu: 9000
```

### Key Configuration Notes

| Parameter | Requirement | Why |
|-----------|------------|-----|
| `new_memory: true` | **Required** | `--legacy-mem` is incompatible with DPDK 25.07 |
| `port_mtu: 9000` | Recommended | Default 65518 causes `dev_configure` error on MLX5 |
| `c: N` | Set to desired cores | Number of worker cores per port pair |
| `--mlx5-so` | **Required** for ConnectX | Loads the MLX5 PMD shared library |

### Prerequisites

- Docker with `--privileged` access
- Hugepages allocated: `echo 4096 > /proc/sys/vm/nr_hugepages`
- `/dev/hugepages`, `/dev/infiniband`, `/sys` accessible to container
- ConnectX NIC with `mlx5_core` kernel driver loaded

## Sending Traffic (Python API)

```python
import sys
sys.path.insert(0, "/opt/trex/scripts/automation/trex_control_plane/interactive")
from trex.stl.api import *

c = STLClient(server="127.0.0.1")
c.connect()
c.reset()

pkt = STLPktBuilder(
    pkt=Ether()/IP(src="10.0.1.100", dst="10.10.1.1")/UDP(dport=12, sport=1025)/Raw(b"x"*16)
)
c.add_streams(STLStream(packet=pkt, mode=STLTXCont(pps=1000000)), ports=[0])
c.start(ports=[0], duration=10)
c.wait_on_traffic()
print(c.get_stats())
c.disconnect()
```

Benchmark scripts are in the `scripts/` directory:
- `scripts/send_traffic.py` - Simple 1 Mpps test
- `scripts/bench_64b_v2.py` - 64B multi-flow dual-port max rate
- `scripts/pkt_size_sweep.py` - Full packet size sweep (64-1518B)

## Performance Results

Tested on DGX Spark (ARM Cortex-X925/A725, ConnectX-7 200G) with
VPP v26.02 as DUT performing L3 IPv4 forwarding with ECMP:

| Packet Size | TRex TX Mpps | TX Gbps | Notes |
|-------------|-------------|---------|-------|
| 64B         | 127         | 65      | NIC TX limit (~55 Mpps/port) |
| 128B        | 99          | 101     | |
| 256B        | 52          | 107     | |
| 512B        | 46          | 189     | |
| 1518B       | 16.2        | 194     | Approaching 200G line rate |

Configuration: 9 TRex worker cores, 2 ports (dual PCIe domain), ConnectX-7.

## What Was Changed from Upstream

### Build System (`linux_dpdk/ws_main.py`)
- Fixed `rte_config.h` path for aarch64 (`dpdk_2507_aarch64/` directory)
- Added `ALLOW_INTERNAL_API` and `ABI_VERSION` to aarch64 DPDK flags
- Enabled MLX5 build for aarch64 (was disabled by default)
- Moved x86-only `-mrtm` flag out of global gcc_flags
- Split `dpdk_src_x86_64` into portable NIC drivers + x86-only SSE/EAL files
- Added aarch64 GCC compatibility flags (`-faligned-new`, `-Wno-dangling-pointer`, etc.)

### New Files
- `Dockerfile` - Multi-stage aarch64 Docker build
- `src/pal/linux_dpdk/dpdk_2507_aarch64/rte_config.h` - DPDK config for ARM64
- `src/pal/linux_dpdk/dpdk_2507_aarch64/rte_build_config.h` - DPDK build config for ARM64
- `src/dpdk/drivers/net/aarch64_vec_stubs.c` - Stubs for x86 SSE vectorized NIC functions

### Runtime Fixes
- `scripts/dpdk_setup_ports.py` - Fixed `Driver_str` KeyError on ARM; enhanced MLX5 detection by device name (ConnectX-5/6/7)
- `scripts/dpdk_nic_bind.py` - Excluded `igb_uio`/`uio_pci_generic` on aarch64 (only `vfio-pci`)
- `scripts/external_libs/pyzmq-ctypes/zmq/arm/64bit/` - Added ARM64 libzmq.so path (populated by Dockerfile)
- `src/pal/linux_dpdk/mbuf.cpp` - Added missing `#include <cstdlib>` for GCC 13+
- `src/stx/common/trex_rx_port_mngr.cpp` - Guarded `bpfjit_*` calls with `#ifdef TREX_USE_BPFJIT`

### Suppressed GCC Warnings

The following GCC warnings are suppressed with `-Wno-*` flags for aarch64
builds. They trigger only at `-O2` on ARM (not x86) and are likely false
positives from GCC 13's more aggressive interprocedural analysis, but
should be investigated if runtime issues occur:

- `-Wno-dangling-pointer` - `trex_rpc_cmd_api.h`
- `-Wno-maybe-uninitialized` - `astf_db.h`
- `-Wno-nonnull` - via `string_fortified.h`

## Troubleshooting

### "ERROR in DPDK map / Could not find requested interface"
- **Missing `--mlx5-so` flag.** The MLX5 PMD is a shared library that must be
  explicitly loaded. Use `--mlx5-so` on the command line or let the `t-rex-64`
  wrapper auto-detect it.
- **No free hugepages.** Check `cat /proc/meminfo | grep HugePages_Free`. Clean
  up stale mappings: `rm -f /dev/hugepages/rtemap_*` (may need root/privileged container).

### "KeyError: 'Driver_str'" in dpdk_setup_ports.py
This was fixed in this fork. If you see it, ensure you're using this patched version.

### "libzmq.so: cannot open shared object file" in Python API
The Dockerfile populates `arm/64bit/libzmq.so` automatically. If running outside
Docker, symlink your system libzmq:
```bash
mkdir -p scripts/external_libs/pyzmq-ctypes/zmq/arm/64bit
ln -s /usr/lib/aarch64-linux-gnu/libzmq.so.5 scripts/external_libs/pyzmq-ctypes/zmq/arm/64bit/libzmq.so
```

### "ZMQ: Address already in use"
A previous TRex instance is still running. Stop it: `docker stop trex`

### MLX5 "Rx queue stop is only supported for non-vectorized single-packet Rx"
This is a harmless warning from the MLX5 PMD. It does not affect functionality.

## Repository

- Upstream: https://github.com/cisco-system-traffic-generator/trex-core
- This fork: https://github.com/ayourtch-llm/trex-arm64-spark
- Based on: TRex v3.08 with DPDK 25.07
