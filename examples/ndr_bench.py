#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = ["pyzmq", "scapy"]
# ///
"""
NDR (No Drop Rate) benchmark with IMIX support.

Uses two TRex instances: TX side (generator) and RX side (counter).
Performs binary search to find the maximum rate with zero packet loss.

Usage:
  uv run examples/ndr_bench.py --tx-server gx10-96b6 --rx-server gx10-bb6a

Topology:
  TRex TX (96b6) --> VPP DUT (be8b) --> TRex RX (bb6a)
"""
import argparse
import sys
import os
import time

def setup_trex_api():
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


# IMIX profiles (name -> list of (size_bytes, weight))
IMIX_PROFILES = {
    "imix": [(64, 7), (570, 4), (1518, 1)],       # Classic IMIX
    "imix-simple": [(64, 58), (594, 33), (1518, 9)],  # Simplified IMIX (Spirent)
    "64": [(64, 1)],
    "128": [(128, 1)],
    "256": [(256, 1)],
    "512": [(512, 1)],
    "1518": [(1518, 1)],
}


def build_streams(STLStream, STLTXCont, STLPktBuilder, STLScVmRaw,
                  STLVmFlowVar, STLVmWrFlowVar, STLVmFixIpv4,
                  Ether, IP, UDP, Raw,
                  profile_name, src_net, dst_ip, target_pps):
    """Build TRex streams for a given IMIX profile."""
    profile = IMIX_PROFILES[profile_name]
    total_weight = sum(w for _, w in profile)
    streams = []

    for size, weight in profile:
        pad_len = max(0, size - 42 - 4)
        frac = weight / total_weight
        pps = int(target_pps * frac)

        vm = STLScVmRaw([
            STLVmFlowVar(name="src", min_value="%s.1" % src_net,
                         max_value="%s.254" % src_net, size=4, op="inc"),
            STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
            STLVmFixIpv4(offset="IP")
        ])
        pkt = STLPktBuilder(
            pkt=Ether()/IP(src="%s.100" % src_net, dst=dst_ip)/
                UDP(dport=12, sport=1025)/Raw(b"x" * pad_len),
            vm=vm
        )
        streams.append(STLStream(packet=pkt, mode=STLTXCont(pps=max(1, pps))))

    return streams


def run_trial(tx_client, rx_client, tx_ports, rx_ports,
              profile_name, target_pps, duration, settle,
              STLStream, STLTXCont, STLPktBuilder, STLScVmRaw,
              STLVmFlowVar, STLVmWrFlowVar, STLVmFixIpv4,
              Ether, IP, UDP, Raw,
              src_nets, dst_ip):
    """Run a single trial at given rate. Returns (tx_pkts, rx_pkts, loss_pct)."""
    tx_client.reset()
    rx_client.reset()

    # Set up TX streams
    per_port_pps = target_pps // len(tx_ports)
    for port in tx_ports:
        net = src_nets[port]
        streams = build_streams(STLStream, STLTXCont, STLPktBuilder,
                                STLScVmRaw, STLVmFlowVar, STLVmWrFlowVar,
                                STLVmFixIpv4, Ether, IP, UDP, Raw,
                                profile_name, net, dst_ip, per_port_pps)
        tx_client.add_streams(streams, ports=[port])

    # Clear RX stats
    rx_client.clear_stats()

    # Start TX
    tx_client.start(ports=tx_ports, duration=duration)

    # Wait for traffic to finish
    time.sleep(settle)
    tx_client.wait_on_traffic(ports=tx_ports)
    time.sleep(1)  # drain

    # Collect stats
    tx_stats = tx_client.get_stats()
    rx_stats = rx_client.get_stats()

    tx_pkts = sum(tx_stats[p]["opackets"] for p in tx_ports)
    rx_pkts = sum(rx_stats[p]["ipackets"] for p in rx_ports)

    loss = tx_pkts - rx_pkts
    loss_pct = (loss / tx_pkts * 100) if tx_pkts > 0 else 0

    return tx_pkts, rx_pkts, loss_pct


def find_ndr(tx_client, rx_client, tx_ports, rx_ports,
             profile_name, max_pps, duration, settle, threshold_pct,
             api_imports, src_nets, dst_ip):
    """Binary search for NDR (No Drop Rate)."""
    (STLStream, STLTXCont, STLPktBuilder, STLScVmRaw,
     STLVmFlowVar, STLVmWrFlowVar, STLVmFixIpv4,
     Ether, IP, UDP, Raw) = api_imports

    lo = 0
    hi = max_pps
    best_ndr = 0
    iteration = 0

    print("\n" + "=" * 75)
    print("NDR Binary Search: %s profile, threshold=%.3f%%, duration=%ds" % (
        profile_name, threshold_pct, duration))
    print("=" * 75)
    print("%-4s %12s %12s %12s %8s %8s" % (
        "#", "Rate Mpps", "TX pkts", "RX pkts", "Loss%", "Result"))
    print("-" * 75)

    while (hi - lo) > max_pps * 0.01:  # converge to 1% resolution
        iteration += 1
        mid = (lo + hi) // 2

        tx_pkts, rx_pkts, loss_pct = run_trial(
            tx_client, rx_client, tx_ports, rx_ports,
            profile_name, mid, duration, settle,
            STLStream, STLTXCont, STLPktBuilder, STLScVmRaw,
            STLVmFlowVar, STLVmWrFlowVar, STLVmFixIpv4,
            Ether, IP, UDP, Raw, src_nets, dst_ip)

        passed = loss_pct <= threshold_pct
        result = "PASS" if passed else "FAIL"

        print("%-4d %12.2f %12d %12d %7.3f%% %8s" % (
            iteration, mid / 1e6, tx_pkts, rx_pkts, loss_pct, result))

        if passed:
            best_ndr = mid
            lo = mid
        else:
            hi = mid

    return best_ndr


def main():
    parser = argparse.ArgumentParser(
        description="NDR benchmark with IMIX support (two TRex instances)")
    parser.add_argument("--tx-server", required=True,
                        help="TRex TX server IP/hostname")
    parser.add_argument("--rx-server", required=True,
                        help="TRex RX server IP/hostname")
    parser.add_argument("--profile", default="imix",
                        choices=list(IMIX_PROFILES.keys()),
                        help="Traffic profile (default: imix)")
    parser.add_argument("--max-pps", type=int, default=100000000,
                        help="Maximum total pps to try (default: 100M)")
    parser.add_argument("--duration", type=int, default=10,
                        help="Trial duration in seconds (default: 10)")
    parser.add_argument("--threshold", type=float, default=0.001,
                        help="Loss threshold %% for pass (default: 0.001)")
    parser.add_argument("--tx-ports", default="0,1",
                        help="TX ports (default: 0,1)")
    parser.add_argument("--rx-ports", default="0,1",
                        help="RX ports (default: 0,1)")
    parser.add_argument("--dst-ip", default="10.10.1.1",
                        help="Destination IP (default: 10.10.1.1)")
    parser.add_argument("--src-net-0", default="10.0.1",
                        help="Source /24 prefix for TX port 0 (default: 10.0.1)")
    parser.add_argument("--src-net-1", default="10.0.3",
                        help="Source /24 prefix for TX port 1 (default: 10.0.3)")
    parser.add_argument("--sweep", action="store_true",
                        help="Run NDR for all standard sizes + IMIX")
    args = parser.parse_args()

    if not setup_trex_api():
        print("ERROR: Could not find TRex Python API.")
        sys.exit(1)

    from trex.stl.api import (STLClient, STLStream, STLTXCont,
                               STLPktBuilder, STLScVmRaw, STLVmFlowVar,
                               STLVmWrFlowVar, STLVmFixIpv4,
                               Ether, IP, UDP, Raw)

    api_imports = (STLStream, STLTXCont, STLPktBuilder, STLScVmRaw,
                   STLVmFlowVar, STLVmWrFlowVar, STLVmFixIpv4,
                   Ether, IP, UDP, Raw)

    tx_ports = [int(p) for p in args.tx_ports.split(",")]
    rx_ports = [int(p) for p in args.rx_ports.split(",")]
    src_nets = {0: args.src_net_0, 1: args.src_net_1}

    print("Connecting to TX TRex at %s..." % args.tx_server)
    tx = STLClient(server=args.tx_server)
    tx.connect()

    print("Connecting to RX TRex at %s..." % args.rx_server)
    rx = STLClient(server=args.rx_server)
    rx.connect()

    # Verify connectivity
    tx.reset()
    rx.reset()
    print("TX ports: %s  RX ports: %s" % (tx_ports, rx_ports))

    profiles = [args.profile]
    if args.sweep:
        profiles = ["64", "128", "256", "512", "1518", "imix"]

    results = []

    for profile in profiles:
        # Calculate sensible max_pps based on profile
        max_pps = args.max_pps
        if profile != "imix":
            size = int(profile)
            l1_bits = (size + 20) * 8
            line_rate_pps = int(200e9 / l1_bits)
            # 2 ports, 90% of line rate as upper bound
            max_pps = min(max_pps, line_rate_pps * 2 * 90 // 100)

        ndr = find_ndr(tx, rx, tx_ports, rx_ports,
                       profile, max_pps, args.duration, 1,
                       args.threshold, api_imports, src_nets, args.dst_ip)

        ndr_mpps = ndr / 1e6
        # Estimate Gbps from average packet size
        profile_sizes = IMIX_PROFILES[profile]
        avg_size = sum(s * w for s, w in profile_sizes) / sum(w for _, w in profile_sizes)
        ndr_gbps = ndr * avg_size * 8 / 1e9

        results.append((profile, ndr_mpps, ndr_gbps))
        print("\n  >>> NDR for %s: %.2f Mpps (%.1f Gbps)\n" % (
            profile, ndr_mpps, ndr_gbps))

    # Summary
    print("\n" + "=" * 55)
    print("NDR Summary (threshold=%.3f%%)" % args.threshold)
    print("=" * 55)
    print("%-12s %12s %12s" % ("Profile", "NDR Mpps", "NDR Gbps"))
    print("-" * 40)
    for profile, mpps, gbps in results:
        print("%-12s %12.2f %12.1f" % (profile, mpps, gbps))
    print("-" * 40)

    tx.disconnect()
    rx.disconnect()
    print("\nDone!")


if __name__ == "__main__":
    main()
