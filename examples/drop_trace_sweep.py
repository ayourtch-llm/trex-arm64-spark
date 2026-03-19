#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = ["pyzmq", "scapy"]
# ///
"""
Drop tracer sweep: runs at ~110% of NDR for each packet size
to see where drops happen across the entire range.
"""
import argparse
import sys
import os
import time
import subprocess

def setup_trex_api():
    for path in ["/opt/trex/scripts/automation/trex_control_plane/interactive",
                 os.path.join(os.path.dirname(__file__), "..", "scripts",
                              "automation", "trex_control_plane", "interactive")]:
        path = os.path.normpath(path)
        if os.path.exists(os.path.join(path, "trex", "stl", "api.py")):
            ext_libs = os.path.normpath(os.path.join(path, "..", "..", "..", "external_libs"))
            if os.path.exists(ext_libs):
                os.environ["TREX_EXT_LIBS"] = ext_libs
            sys.path.insert(0, path)
            return True
    return False

def ssh_cmd(host, cmd):
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=3", host, cmd],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception as e:
        return "ERROR: %s" % e

def parse_ethtool(text):
    d = {}
    for line in text.strip().split("\n"):
        if ":" in line:
            k, v = line.strip().split(":", 1)
            try:
                d[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return d

def get_nic_snapshot(host):
    """Snapshot all 4 NIC port ethtool counters."""
    snap = {}
    for name, iface in [("nic1-in", "enp1s0f0np0"), ("nic1-out", "enp1s0f1np1"),
                         ("nic2-in", "enP2p1s0f0np0"), ("nic2-out", "enP2p1s0f1np1")]:
        raw = ssh_cmd(host, "ethtool -S %s 2>/dev/null | grep -E 'discards|out_of_buffer|errors_phy|packets_phy'" % iface)
        snap[name] = parse_ethtool(raw)
    return snap

def nic_deltas(before, after):
    """Compute deltas between two NIC snapshots."""
    result = {}
    for name in before:
        result[name] = {}
        for k in after.get(name, {}):
            delta = after[name].get(k, 0) - before[name].get(k, 0)
            if delta != 0:
                result[name][k] = delta
    return result


def run_drop_test(tx, rx, vpp_host, size, rate_mpps, duration,
                  STLStream, STLTXCont, STLPktBuilder, STLScVmRaw,
                  STLVmFlowVar, STLVmWrFlowVar, STLVmFixIpv4,
                  Ether, IP, UDP, Raw):
    """Run a single drop test and return structured results."""
    tx.reset()
    rx.reset()
    rx.clear_stats()

    per_port_pps = int(rate_mpps * 1e6) // 2
    pad_len = max(0, size - 42 - 4)

    for port, net in [(0, "10.0.1"), (1, "10.0.3")]:
        vm = STLScVmRaw([
            STLVmFlowVar(name="src", min_value="%s.1" % net,
                         max_value="%s.254" % net, size=4, op="inc"),
            STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
            STLVmFixIpv4(offset="IP")
        ])
        pkt = STLPktBuilder(
            pkt=Ether()/IP(src="%s.100" % net, dst="10.10.1.1")/
                UDP(dport=12, sport=1025)/Raw(b"x" * pad_len),
            vm=vm
        )
        tx.add_streams(STLStream(packet=pkt, mode=STLTXCont(pps=per_port_pps)),
                       ports=[port])

    # Clear VPP counters
    ssh_cmd(vpp_host, "docker exec vpp-uut vppctl clear interfaces")

    # Snapshot NIC counters before
    nic_before = get_nic_snapshot(vpp_host)

    # Run
    tx.start(ports=[0, 1], duration=duration)
    tx.wait_on_traffic(ports=[0, 1])
    time.sleep(1)

    # Collect
    tx_stats = tx.get_stats()
    rx_stats = rx.get_stats()
    nic_after = get_nic_snapshot(vpp_host)
    vpp_raw = ssh_cmd(vpp_host, "docker exec vpp-uut vppctl show interface")

    # Parse VPP rx-miss
    rx_miss_total = 0
    for line in vpp_raw.split("\n"):
        if "rx-miss" in line:
            parts = line.strip().split()
            rx_miss_total += int(parts[-1])

    # Compute
    tx_total = tx_stats[0]["opackets"] + tx_stats[1]["opackets"]
    rx_total = rx_stats[0]["ipackets"] + rx_stats[1]["ipackets"]
    nd = nic_deltas(nic_before, nic_after)

    nic_rx_discards = sum(nd[n].get("rx_discards_phy", 0)
                          for n in ["nic1-in", "nic2-in"])
    nic_rx_oob = sum(nd[n].get("rx_out_of_buffer", 0)
                     for n in ["nic1-in", "nic2-in"])
    nic_rx_pkts = sum(nd[n].get("rx_packets_phy", 0)
                      for n in ["nic1-in", "nic2-in"])
    nic_tx_pkts = sum(nd[n].get("tx_packets_phy", 0)
                      for n in ["nic1-out", "nic2-out"])
    nic_tx_errors = sum(nd[n].get("tx_errors_phy", 0)
                        for n in ["nic1-out", "nic2-out"])

    return {
        "size": size,
        "rate_mpps": rate_mpps,
        "tx_total": tx_total,
        "rx_total": rx_total,
        "loss": tx_total - rx_total,
        "loss_pct": (tx_total - rx_total) / tx_total * 100 if tx_total else 0,
        "nic_rx_pkts": nic_rx_pkts,
        "nic_rx_discards": nic_rx_discards,
        "nic_rx_oob": nic_rx_oob,
        "nic_tx_pkts": nic_tx_pkts,
        "nic_tx_errors": nic_tx_errors,
        "vpp_rx_miss": rx_miss_total,
        "nic_deltas": nd,
    }


def main():
    parser = argparse.ArgumentParser(description="Drop tracer sweep")
    parser.add_argument("--tx-server", required=True)
    parser.add_argument("--rx-server", required=True)
    parser.add_argument("--vpp-host", required=True)
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--overhead", type=float, default=1.10,
                        help="Rate multiplier above NDR (default: 1.10 = 110%%)")
    args = parser.parse_args()

    if not setup_trex_api():
        print("ERROR: TRex API not found"); sys.exit(1)

    from trex.stl.api import (STLClient, STLStream, STLTXCont,
                               STLPktBuilder, STLScVmRaw, STLVmFlowVar,
                               STLVmWrFlowVar, STLVmFixIpv4,
                               Ether, IP, UDP, Raw)

    api = (STLStream, STLTXCont, STLPktBuilder, STLScVmRaw,
           STLVmFlowVar, STLVmWrFlowVar, STLVmFixIpv4,
           Ether, IP, UDP, Raw)

    # Approximate NDR values from previous runs (Mpps)
    ndr_estimates = {
        64: 90,
        128: 87,
        256: 72,
        512: 43,
        1518: 15.5,
    }

    print("Connecting to TRex TX at %s..." % args.tx_server)
    tx = STLClient(server=args.tx_server)
    tx.connect()

    print("Connecting to TRex RX at %s..." % args.rx_server)
    rx = STLClient(server=args.rx_server)
    rx.connect()

    print("\n" + "=" * 110)
    print("Drop Tracer Sweep (rate = %.0f%% of estimated NDR, %ds per size)" % (
        args.overhead * 100, args.duration))
    print("=" * 110)

    # Header
    print("\n%-6s %8s %12s %12s %10s %14s %12s %12s" % (
        "Size", "Rate", "TX pkts", "RX pkts", "Loss%",
        "NIC rx_discard", "NIC rx_oob", "VPP rx-miss"))
    print("-" * 110)

    all_results = []

    for size in [64, 128, 256, 512, 1518]:
        ndr = ndr_estimates[size]
        rate = round(ndr * args.overhead, 1)

        # Cap at line rate
        l1_bits = (size + 20) * 8
        max_rate = int(200e9 / l1_bits * 2 * 0.95) / 1e6
        rate = min(rate, max_rate)

        r = run_drop_test(tx, rx, args.vpp_host, size, rate, args.duration, *api)
        all_results.append(r)

        print("%-6d %7.1fM %12d %12d %9.3f%% %14d %12d %12d" % (
            size, rate, r["tx_total"], r["rx_total"], r["loss_pct"],
            r["nic_rx_discards"], r["nic_rx_oob"], r["vpp_rx_miss"]))

    print("-" * 110)

    # Detailed breakdown
    print("\n" + "=" * 110)
    print("Detailed NIC Hardware Counter Deltas")
    print("=" * 110)

    for r in all_results:
        print("\n--- %dB at %.1f Mpps (loss: %.3f%%) ---" % (
            r["size"], r["rate_mpps"], r["loss_pct"]))
        for nic_name in ["nic1-in", "nic2-in", "nic1-out", "nic2-out"]:
            deltas = r["nic_deltas"].get(nic_name, {})
            if deltas:
                items = ["  %s: %s" % (nic_name, ", ".join(
                    "%s=%d" % (k, v) for k, v in sorted(deltas.items())))]
                print(items[0])

    # Analysis
    print("\n" + "=" * 110)
    print("Analysis")
    print("=" * 110)
    for r in all_results:
        print("\n%dB:" % r["size"])
        total_loss = r["loss"]
        if total_loss <= 0:
            print("  No drops at %.1f Mpps" % r["rate_mpps"])
            continue

        if r["nic_rx_discards"] > 0:
            pct_of_loss = r["nic_rx_discards"] / total_loss * 100 if total_loss else 0
            print("  NIC RX discards: %d (%.0f%% of total loss)" % (
                r["nic_rx_discards"], pct_of_loss))
            print("    -> NIC can't drain RX ring fast enough (PCIe BW / descriptor rate)")

        if r["vpp_rx_miss"] > 0:
            print("  VPP rx-miss: %d" % r["vpp_rx_miss"])
            print("    -> DPDK poll missed packets (worker cores busy or ring too small)")

        if r["nic_rx_oob"] > 0:
            print("  NIC rx_out_of_buffer: %d" % r["nic_rx_oob"])
            print("    -> NIC ran out of RX buffer descriptors")

        if r["nic_tx_errors"] > 0:
            print("  NIC TX errors: %d" % r["nic_tx_errors"])
            print("    -> Egress path dropping")

        # PCIe bandwidth estimate
        pcie_rx_bytes = r["nic_rx_pkts"] * (r["size"] + 20)  # +overhead
        pcie_tx_bytes = r["nic_tx_pkts"] * (r["size"] + 20)
        pcie_total_gbps = (pcie_rx_bytes + pcie_tx_bytes) * 8 / 1e9 / args.duration
        print("  Estimated PCIe load: %.1f Gbps (RX+TX combined per %ds)" % (
            pcie_total_gbps, args.duration))

    tx.disconnect()
    rx.disconnect()
    print("\nDone!")


if __name__ == "__main__":
    main()
