#!/usr/bin/env python3
"""TRex packet size sweep: 64, 128, 256, 512, 1518 bytes at max rate"""
import sys, time
sys.path.insert(0, "/opt/trex/scripts/automation/trex_control_plane/interactive")
from trex.stl.api import *

SIZES = [64, 128, 256, 512, 1518]
DURATION = 15  # seconds per size
SETTLE = 3     # seconds to settle before measuring

c = STLClient(server="127.0.0.1")
c.connect()

print("=" * 70)
print("TRex Packet Size Sweep - DGX Spark ConnectX-7 -> VPP2 L3 fwd")
print("=" * 70)
print("%-8s %12s %12s %12s %12s" % ("PktSize", "TX Mpps", "TX Gbps", "TX pkts", "Duration"))
print("-" * 70)

results = []

for size in SIZES:
    c.reset()

    # Calculate padding to reach target size (Ether=14 + IP=20 + UDP=8 + FCS=4 = 46 overhead)
    # DPDK doesn't count FCS in packet size, so overhead = 14+20+8 = 42
    pad_len = max(0, size - 42 - 4)  # -4 for FCS that wire adds

    # Port 0: vary src IP for ECMP
    vm0 = STLScVmRaw([
        STLVmFlowVar(name="src", min_value="10.0.1.1", max_value="10.0.1.254", size=4, op="inc"),
        STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
        STLVmFixIpv4(offset="IP")
    ])
    pkt0 = STLPktBuilder(
        pkt=Ether()/IP(src="10.0.1.100", dst="10.10.1.1")/UDP(dport=12, sport=1025)/Raw(b"x" * pad_len),
        vm=vm0
    )

    # Port 1: vary src IP
    vm1 = STLScVmRaw([
        STLVmFlowVar(name="src", min_value="10.0.3.1", max_value="10.0.3.254", size=4, op="inc"),
        STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
        STLVmFixIpv4(offset="IP")
    ])
    pkt1 = STLPktBuilder(
        pkt=Ether()/IP(src="10.0.3.100", dst="10.10.1.1")/UDP(dport=12, sport=1025)/Raw(b"x" * pad_len),
        vm=vm1
    )

    # Calculate max pps per port that fits in 200G line rate
    # L1 size = pkt + 20 (preamble+IFG) bytes, in bits
    l1_bits = (size + 20) * 8
    max_pps_per_port = int(200e9 / l1_bits * 0.95)  # 95% of line rate
    target_pps = min(100000000, max_pps_per_port)

    c.add_streams(STLStream(packet=pkt0, mode=STLTXCont(pps=target_pps)), ports=[0])
    c.add_streams(STLStream(packet=pkt1, mode=STLTXCont(pps=target_pps)), ports=[1])

    c.start(ports=[0, 1], duration=DURATION)

    # Wait for settle
    time.sleep(SETTLE)

    # Sample stats over measurement window
    samples = []
    for i in range(3):
        time.sleep(2)
        stats = c.get_stats()
        g = stats["global"]
        tx_mpps = g.get("tx_pps", 0) / 1e6
        tx_gbps = g.get("tx_bps", 0) / 1e9
        samples.append((tx_mpps, tx_gbps))

    c.wait_on_traffic()
    final = c.get_stats()

    # Use average of samples for rate
    avg_mpps = sum(s[0] for s in samples) / len(samples)
    avg_gbps = sum(s[1] for s in samples) / len(samples)
    total_tx = final[0]["opackets"] + final[1]["opackets"]

    print("%-8d %12.2f %12.1f %12d %12ds" % (size, avg_mpps, avg_gbps, total_tx, DURATION))
    results.append((size, avg_mpps, avg_gbps, total_tx))

    time.sleep(2)  # cooldown

print("-" * 70)
print("\n=== Summary (compare with testpmd baseline) ===")
print("%-8s %12s %12s" % ("PktSize", "TRex Mpps", "TRex Gbps"))
print("-" * 40)
for size, mpps, gbps, _ in results:
    print("%-8d %12.2f %12.1f" % (size, mpps, gbps))

c.disconnect()
print("\nDone!")
