#!/usr/bin/env python3
"""TRex benchmark: 64B multi-flow on both ports, max rate for 10s"""
import sys
sys.path.insert(0, "/opt/trex/scripts/automation/trex_control_plane/interactive")
from trex.stl.api import *
import time

c = STLClient(server="127.0.0.1")
c.connect()
c.reset()

# Port 0: 64B UDP, varying src IP for ECMP distribution
pkt0 = STLPktBuilder(
    pkt=Ether()/IP(src="10.0.1.100", dst="10.10.1.1")/UDP(dport=12, sport=1025)/Raw(b"x"*16)
)
# Field engine: vary src IP to spread across ECMP paths
vm0 = STLScVmRaw([
    STLVmFlowVar(name="src", min_value="10.0.1.1", max_value="10.0.1.254",
                 size=4, op="inc"),
    STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
    STLVmFixIpv4(offset="IP")
])
pkt0_vm = STLPktBuilder(
    pkt=Ether()/IP(src="10.0.1.100", dst="10.10.1.1")/UDP(dport=12, sport=1025)/Raw(b"x"*16),
    vm=vm0
)

# Port 1: same but from other subnet
vm1 = STLScVmRaw([
    STLVmFlowVar(name="src", min_value="10.0.3.1", max_value="10.0.3.254",
                 size=4, op="inc"),
    STLVmWrFlowVar(fv_name="src", pkt_offset="IP.src"),
    STLVmFixIpv4(offset="IP")
])
pkt1_vm = STLPktBuilder(
    pkt=Ether()/IP(src="10.0.3.100", dst="10.10.1.1")/UDP(dport=12, sport=1025)/Raw(b"x"*16),
    vm=vm1
)

s0 = STLStream(packet=pkt0_vm, mode=STLTXCont())
s1 = STLStream(packet=pkt1_vm, mode=STLTXCont())

c.add_streams(s0, ports=[0])
c.add_streams(s1, ports=[1])

# Clear VPP stats would be nice but we can check deltas
print("Starting max rate 64B on both ports for 10 seconds...")
c.start(ports=[0, 1], mult="100%", duration=10)

# Poll stats every 2 seconds
for i in range(5):
    time.sleep(2)
    stats = c.get_stats()
    g = stats["global"]
    tx_mpps = g.get("tx_pps", 0) / 1e6
    tx_gbps = g.get("tx_bps", 0) / 1e9
    rx_mpps = g.get("rx_pps", 0) / 1e6
    print("  [%ds] TX: %.2f Mpps (%.1f Gbps)  RX: %.2f Mpps" % ((i+1)*2, tx_mpps, tx_gbps, rx_mpps))

c.wait_on_traffic()
stats = c.get_stats()

print("\n=== Final Stats ===")
for port in [0, 1]:
    p = stats[port]
    print("Port %d: TX %d pkts (%d bytes), RX %d pkts" % (
        port, p["opackets"], p["obytes"], p["ipackets"]))

g = stats["global"]
print("\nGlobal: TX %.2f Mpps (%.1f Gbps)" % (
    g.get("tx_pps", 0)/1e6, g.get("tx_bps", 0)/1e9))

c.disconnect()
print("Done!")
