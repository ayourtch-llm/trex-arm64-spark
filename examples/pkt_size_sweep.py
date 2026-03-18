#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = ["pyzmq", "scapy"]
# ///
"""
TRex packet size sweep - tests 64, 128, 256, 512, 1518B at max rate.

Usage:
  uv run pkt_size_sweep.py --server 10.0.0.1

Or inside the TRex container:
  docker exec trex python3 /opt/trex/examples/pkt_size_sweep.py

Prerequisites:
  - TRex server running with dual ports (see main README)
  - uv installed: curl -LsSf https://astral.sh/uv/install.sh | sh
  - Network access to TRex host on ports 4500/4501
"""
import argparse
import sys
import os
import time

def setup_trex_api():
    """Find and add TRex Python API to sys.path."""
    search_paths = [
        "/opt/trex/scripts/automation/trex_control_plane/interactive",
        os.path.join(os.path.dirname(__file__), "..", "scripts",
                     "automation", "trex_control_plane", "interactive"),
    ]
    for path in search_paths:
        path = os.path.normpath(path)
        if os.path.exists(os.path.join(path, "trex", "stl", "api.py")):
            ext_libs = os.path.normpath(os.path.join(
                path, "..", "..", "..", "external_libs"))
            if os.path.exists(ext_libs):
                os.environ["TREX_EXT_LIBS"] = ext_libs
            sys.path.insert(0, path)
            return True
    return False

def main():
    parser = argparse.ArgumentParser(description="TRex packet size sweep")
    parser.add_argument("--server", default="127.0.0.1",
                        help="TRex server IP (default: 127.0.0.1)")
    parser.add_argument("--duration", type=int, default=15,
                        help="Duration per packet size in seconds (default: 15)")
    parser.add_argument("--ports", default="0,1",
                        help="TX ports, comma-separated (default: 0,1)")
    parser.add_argument("--src-net-port0", default="10.0.1",
                        help="Source IP /24 prefix for port 0 (default: 10.0.1)")
    parser.add_argument("--src-net-port1", default="10.0.3",
                        help="Source IP /24 prefix for port 1 (default: 10.0.3)")
    parser.add_argument("--dst-ip", default="10.10.1.1",
                        help="Destination IP (default: 10.10.1.1)")
    args = parser.parse_args()

    if not setup_trex_api():
        print("ERROR: Could not find TRex Python API.")
        sys.exit(1)

    from trex.stl.api import (STLClient, STLStream, STLTXCont,
                               STLPktBuilder, STLScVmRaw, STLVmFlowVar,
                               STLVmWrFlowVar, STLVmFixIpv4,
                               Ether, IP, UDP, Raw)

    ports = [int(p) for p in args.ports.split(",")]
    sizes = [64, 128, 256, 512, 1518]
    settle = 3

    c = STLClient(server=args.server)
    print("Connecting to TRex server at %s..." % args.server)
    c.connect()

    src_nets = {
        ports[0]: args.src_net_port0,
    }
    if len(ports) > 1:
        src_nets[ports[1]] = args.src_net_port1

    print("=" * 70)
    print("TRex Packet Size Sweep")
    print("  Ports: %s  Duration: %ds/size  Server: %s" % (
        ports, args.duration, args.server))
    print("=" * 70)
    print("%-8s %12s %12s %12s" % ("PktSize", "TX Mpps", "TX Gbps", "TX pkts"))
    print("-" * 52)

    results = []

    for size in sizes:
        c.reset()

        for port in ports:
            net = src_nets.get(port, args.src_net_port0)
            pad_len = max(0, size - 42 - 4)

            vm = STLScVmRaw([
                STLVmFlowVar(name="src", min_value="%s.1" % net,
                             max_value="%s.254" % net, size=4, op="inc"),
                STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
                STLVmFixIpv4(offset="IP")
            ])
            pkt = STLPktBuilder(
                pkt=Ether()/IP(src="%s.100" % net, dst=args.dst_ip)/
                    UDP(dport=12, sport=1025)/Raw(b"x" * pad_len),
                vm=vm
            )

            # Cap rate at 95% line rate per port
            l1_bits = (size + 20) * 8
            max_pps = int(200e9 / l1_bits * 0.95)
            target_pps = min(100000000, max_pps)

            c.add_streams(STLStream(packet=pkt, mode=STLTXCont(pps=target_pps)),
                          ports=[port])

        c.start(ports=ports, duration=args.duration)
        time.sleep(settle)

        # Sample 3 times over measurement window
        samples = []
        for _ in range(3):
            time.sleep(2)
            stats = c.get_stats()
            g = stats["global"]
            samples.append((g.get("tx_pps", 0) / 1e6, g.get("tx_bps", 0) / 1e9))

        c.wait_on_traffic()
        final = c.get_stats()

        avg_mpps = sum(s[0] for s in samples) / len(samples)
        avg_gbps = sum(s[1] for s in samples) / len(samples)
        total_tx = sum(final[p]["opackets"] for p in ports)

        print("%-8d %12.2f %12.1f %12d" % (size, avg_mpps, avg_gbps, total_tx))
        results.append((size, avg_mpps, avg_gbps, total_tx))
        time.sleep(2)

    print("-" * 52)
    print("\nDone!")

    c.disconnect()

if __name__ == "__main__":
    main()
