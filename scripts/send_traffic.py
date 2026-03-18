#!/usr/bin/env python3
"""Simple TRex traffic test - sends UDP to 10.10.x.x via VPP2 ECMP"""
import sys
sys.path.insert(0, "/opt/trex/scripts/automation/trex_control_plane/interactive")
from trex.stl.api import *
import time

c = STLClient(server="127.0.0.1")
c.connect()
c.reset()

# Simple 64B UDP packet to 10.10.1.1 (routed via VPP2 ECMP)
pkt = STLPktBuilder(
    pkt=Ether()/IP(src="10.0.1.100", dst="10.10.1.1")/UDP(dport=12, sport=1025)/Raw(b"x"*16)
)

# Continuous stream
s1 = STLStream(packet=pkt, mode=STLTXCont(pps=1000000))
c.add_streams(s1, ports=[0])

# Start at 1 Mpps for 10s
print("Starting 1 Mpps on port 0 for 10 seconds...")
c.start(ports=[0], mult="1mpps", duration=10)
c.wait_on_traffic(ports=[0])

stats = c.get_stats()
p0 = stats[0]
p1 = stats[1]
g = stats["global"]

print("\n=== Port 0 (TX) ===")
print("  TX packets: %d" % p0["opackets"])
print("  TX bytes:   %d" % p0["obytes"])

print("\n=== Port 1 ===")
print("  RX packets: %d" % p1["ipackets"])

print("\n=== Global ===")
print("  TX pps: %.0f" % g.get("tx_pps", 0))
print("  RX pps: %.0f" % g.get("rx_pps", 0))
print("  TX bps: %.0f" % g.get("tx_bps", 0))

c.disconnect()
print("\nDone!")
